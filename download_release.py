# SPDX-License-Identifier: Apache-2.0

import os
import hashlib
import shutil
import tempfile
import requests
import time
from optparse import OptionParser

GITHUB_API_URL = "https://api.github.com/repos/xlsynth/xlsynth/releases"
SUPPORTED_PLATFORMS = ["ubuntu2004", "ubuntu2204", "rocky8", "arm64", "x64"]

def get_headers():
    """
    Returns a dictionary of HTTP headers to use in requests.
    If the GH_PAT environment variable is set, it adds the token for authentication.
    """
    gh_pat = os.getenv('GH_PAT')
    if gh_pat:
        return {"Authorization": f"token {gh_pat}"}
    return {}

def request_with_retry(url, stream, headers, max_attempts):
    """
    Attempts to send a GET request to a given URL with exponential backoff.
    Retries up to max_attempts times.
    """
    attempt = 0
    delay = 1  # initial delay in seconds
    while attempt < max_attempts:
        attempt += 1
        try:
            response = requests.get(url, stream=stream, headers=headers)
            # If it's a 404, don't bother retrying.
            if response.status_code == 404:
                print(f"404 Not Found for {url} (not retrying).")
                response.raise_for_status()
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt == max_attempts or (hasattr(e.response, "status_code") and e.response is not None and e.response.status_code == 404):
                print(f"All {attempt} attempts failed for {url}")
                raise
            else:
                print(f"Attempt {attempt} failed for {url}. Error: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # exponential backoff

def get_latest_release(max_attempts):
    print("Discovering the latest release version...")
    print("PAT present? ", os.getenv('GH_PAT') is not None)
    response = request_with_retry(f"{GITHUB_API_URL}/latest", stream=False, headers=get_headers(), max_attempts=max_attempts)
    latest_version = response.json()["tag_name"]
    print(f"Latest version discovered: {latest_version}")
    return latest_version

def high_integrity_download(base_url, filename, target_dir, max_attempts, is_binary=False, platform=None):
    print(f"Starting download of {filename}...")
    start_time = time.time()

    with tempfile.TemporaryDirectory() as temp_dir:
        sha256_url = f"{base_url}/{filename}.sha256"
        artifact_url = f"{base_url}/{filename}"

        sha256_path = os.path.join(temp_dir, f"{filename}.sha256")
        artifact_path = os.path.join(temp_dir, filename)

        headers = get_headers()

        # Download SHA256 file with retry support
        with request_with_retry(sha256_url, stream=True, headers=headers, max_attempts=max_attempts) as r:
            with open(sha256_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

        # Download the artifact with retry support
        with request_with_retry(artifact_url, stream=True, headers=headers, max_attempts=max_attempts) as r:
            with open(artifact_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

        # Verify checksum
        with open(sha256_path, 'r') as f:
            expected_checksum = f.read().strip().split()[0]

        hasher = hashlib.sha256()
        with open(artifact_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        actual_checksum = hasher.hexdigest()

        if expected_checksum != actual_checksum:
            raise ValueError(f"Checksum mismatch for {filename}")

        # Determine target filename
        target_filename = filename
        if is_binary and platform and filename.endswith(f"-{platform}"):
            target_filename = filename[:-(len(platform) + 1)]  # Remove '-platform'

        # Move to target directory
        target_path = os.path.join(target_dir, target_filename)
        shutil.move(artifact_path, target_path)

        # Make binary artifacts executable
        if is_binary:
            os.chmod(target_path, 0o755)

        elapsed_time = time.time() - start_time
        file_size = os.path.getsize(target_path) / (1024 * 1024)  # Size in MiB
        print(f"Downloaded {target_filename}: {file_size:.2f} MiB in {elapsed_time:.2f} seconds")

def main():
    parser = OptionParser()
    parser.add_option("-v", "--version", dest="version", help="Specify release version (e.g., v0.0.0)")
    parser.add_option("-o", "--output", dest="output_dir", help="Output directory for artifacts")
    parser.add_option("-p", "--platform", dest="platform", help="Target platform (e.g., ubuntu2004, rocky8)")
    parser.add_option('--max_attempts', dest='max_attempts', help='Maximum number of attempts to download', type='int', default=10)

    (options, args) = parser.parse_args()

    if args:
        parser.error("No positional arguments are allowed.")

    if not options.output_dir or not options.platform:
        parser.error("output directory argument and -p/--platform flag are required.")

    if options.platform not in SUPPORTED_PLATFORMS:
        parser.error(f"Unsupported platform '{options.platform}'. Supported platforms: {', '.join(SUPPORTED_PLATFORMS)}")

    version = options.version if options.version else get_latest_release(options.max_attempts)

    # It's important to check this so that we get a URL that is actually released and valid.
    assert version.startswith("v"), "Version must start with 'v'"

    base_url = f"https://github.com/xlsynth/xlsynth/releases/download/{version}"

    artifacts = [
        ("dslx_interpreter_main", True),
        ("ir_converter_main", True),
        ("codegen_main", True),
        ("opt_main", True),
        ("prove_quickcheck_main", True),
        ("typecheck_main", True),
        ("dslx_fmt", True),
        ("delay_info_main", True),
        ("check_ir_equivalence_main", True),
    ]

    os.makedirs(options.output_dir, exist_ok=True)

    for artifact, is_binary in artifacts:
        filename = f"{artifact}-{options.platform}"
        high_integrity_download(base_url, filename, options.output_dir, options.max_attempts, is_binary, options.platform)

    # Download and extract dslx_stdlib.tar.gz
    stdlib_filename = "dslx_stdlib.tar.gz"
    high_integrity_download(base_url, stdlib_filename, options.output_dir, options.max_attempts, is_binary=False)
    shutil.unpack_archive(os.path.join(options.output_dir, stdlib_filename), options.output_dir)

if __name__ == "__main__":
    main()
