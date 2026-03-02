# SPDX-License-Identifier: Apache-2.0

import gzip
import hashlib
import http.client
import json
from optparse import OptionParser
import os
import shutil
import tempfile
import time
from urllib import error as urlerror
from urllib import request as urlrequest

GITHUB_API_URL = "https://api.github.com/repos/xlsynth/xlsynth/releases"
SUPPORTED_PLATFORMS = {
    "ubuntu2004": ".so",
    "ubuntu2204": ".so",
    "rocky8": ".so",
    "arm64": ".dylib",
    "x64": ".so",
}

TOOL_BINARIES = [
    "dslx_interpreter_main",
    "ir_converter_main",
    "codegen_main",
    "opt_main",
    "prove_quickcheck_main",
    "typecheck_main",
    "dslx_fmt",
    "delay_info_main",
    "check_ir_equivalence_main",
]


def parse_xlsynth_release_tag(tag):
    assert tag.startswith("v"), "Version tags must start with 'v': {}".format(tag)
    main_and_patch2 = tag[1:].split("-")
    main_parts = main_and_patch2[0].split(".")
    assert len(main_parts) == 3, "Expected semantic version tag, got: {}".format(tag)
    major, minor, patch = main_parts
    patch2 = int(main_and_patch2[1]) if len(main_and_patch2) > 1 else 0
    return (int(major), int(minor), int(patch), patch2)


def build_binary_release_filename(binary_name, platform):
    return "{}-{}".format(binary_name, platform)


def build_dso_release_filename(platform, version_tuple):
    filename = "libxls-{}{}".format(platform, SUPPORTED_PLATFORMS[platform])
    if version_tuple >= (0, 0, 219, 0):
        filename += ".gz"
    return filename


def build_release_artifacts(version, platform, include_dso):
    version_tuple = parse_xlsynth_release_tag(version)
    artifacts = [(build_binary_release_filename(binary_name, platform), True) for binary_name in TOOL_BINARIES]
    if include_dso:
        artifacts.append((build_dso_release_filename(platform, version_tuple), False))
    return artifacts

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
    Attempts to open a URL with exponential backoff using urllib.
    Retries up to max_attempts times. Does not retry on HTTP 404.
    """
    attempt = 0
    delay = 1  # initial delay in seconds
    while attempt < max_attempts:
        attempt += 1
        req = urlrequest.Request(url, headers=headers or {})
        try:
            resp = urlrequest.urlopen(req)
            return resp
        except urlerror.HTTPError as e:
            if e.code == 404 or attempt == max_attempts:
                print(f"All {attempt} attempts failed for {url}")
                raise
            print(f"Attempt {attempt} failed for {url}. HTTP {e.code}. Retrying in {delay} seconds...")
            time.sleep(delay)
            delay *= 2
        except urlerror.URLError as e:
            if attempt == max_attempts:
                print(f"All {attempt} attempts failed for {url}")
                raise
            print(f"Attempt {attempt} failed for {url}. Error: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
            delay *= 2

def get_latest_release(max_attempts):
    print("Discovering the latest release version...")
    print("PAT present? ", os.getenv('GH_PAT') is not None)
    with request_with_retry(f"{GITHUB_API_URL}/latest", stream=False, headers=get_headers(), max_attempts=max_attempts) as r:
        body = r.read().decode('utf-8')
    latest_version = json.loads(body)["tag_name"]
    print(f"Latest version discovered: {latest_version}")
    return latest_version

def copy_url_to_path(url, destination_path, headers, max_attempts):
    """
    Downloads one URL to destination_path with exponential-backoff retries.

    This retries both connection setup failures and mid-stream read failures so
    large artifact downloads survive transient disconnects.
    """
    attempt = 0
    delay = 1
    while attempt < max_attempts:
        attempt += 1
        try:
            with request_with_retry(url, stream=True, headers=headers, max_attempts=max_attempts) as r:
                with open(destination_path, 'wb') as f:
                    shutil.copyfileobj(r, f)
            return
        except urlerror.HTTPError as e:
            if e.code == 404 or attempt == max_attempts:
                print(f"All {attempt} attempts failed for {url}")
                raise
            print(f"Attempt {attempt} failed for {url}. HTTP {e.code}. Retrying in {delay} seconds...")
        except (ConnectionResetError, EOFError, OSError, TimeoutError, http.client.HTTPException, urlerror.URLError) as e:
            if attempt == max_attempts:
                print(f"All {attempt} attempts failed for {url}")
                raise
            print(f"Attempt {attempt} failed for {url}. Error: {e}. Retrying in {delay} seconds...")
        time.sleep(delay)
        delay *= 2

def high_integrity_download(base_url, filename, target_dir, max_attempts, is_binary=False, platform=None):
    print(f"Starting download of {filename}...")
    start_time = time.time()

    with tempfile.TemporaryDirectory() as temp_dir:
        sha256_url = f"{base_url}/{filename}.sha256"
        artifact_url = f"{base_url}/{filename}"

        sha256_path = os.path.join(temp_dir, f"{filename}.sha256")
        artifact_path = os.path.join(temp_dir, filename)

        headers = get_headers()

        copy_url_to_path(sha256_url, sha256_path, headers, max_attempts)

        copy_url_to_path(artifact_url, artifact_path, headers, max_attempts)

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
        is_gz_dso = target_filename.endswith(".so.gz") or target_filename.endswith(".dylib.gz")
        if is_gz_dso:
            target_filename = target_filename[:-3]

        # Move to target directory
        target_path = os.path.join(target_dir, target_filename)
        if is_gz_dso:
            with gzip.open(artifact_path, "rb") as fin, open(target_path, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            os.remove(artifact_path)
        else:
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
    parser.add_option(
        "-d",
        "--dso",
        dest="dso",
        help="Download the libxls dynamic library",
        action="store_true",
        default=False,
    )
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

    artifacts = build_release_artifacts(version, options.platform, options.dso)

    os.makedirs(options.output_dir, exist_ok=True)

    for artifact, is_binary in artifacts:
        high_integrity_download(base_url, artifact, options.output_dir, options.max_attempts, is_binary, options.platform)

    # Download and extract dslx_stdlib.tar.gz
    stdlib_filename = "dslx_stdlib.tar.gz"
    high_integrity_download(base_url, stdlib_filename, options.output_dir, options.max_attempts, is_binary=False)
    shutil.unpack_archive(os.path.join(options.output_dir, stdlib_filename), options.output_dir)

if __name__ == "__main__":
    main()
