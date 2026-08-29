# SPDX-License-Identifier: Apache-2.0

"""Installs the pinned Linux system Bitwuzla libraries used by XLSynth CI."""

import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import download_release


# This is the same Rocky 8 build used by xlsynth-crate v0.66.0's Ubuntu CI,
# including Ubuntu 20.04. Reuse its shared libraries, not Cargo's vendored build.
RELEASE_URL = (
    "https://github.com/xlsynth/boolector-build/releases/download/"
    "bitwuzla-binaries-b29041fbbe6318cb4c19a6e11c7616efc4cb4d32"
)
LIBRARIES = ("bitwuzla", "bitwuzlabb", "bitwuzlabv", "bitwuzlals", "cadical")


def install_shared_libraries(library_dir):
    """Verify every download before installing development names and SONAME links."""
    with tempfile.TemporaryDirectory(prefix = "rules_xlsynth-bitwuzla-") as tempdir:
        staged = []
        for name in LIBRARIES:
            filename = "lib{}-rocky8.so".format(name)
            download_release.high_integrity_download(
                RELEASE_URL, filename, tempdir, max_attempts = 5,
            )
            source = Path(tempdir) / filename
            with source.open("rb") as artifact:
                if artifact.read(4) != b"\x7fELF":
                    raise ValueError("Expected ELF shared library: {}".format(filename))
            staged.append((source, library_dir / "lib{}.so".format(name)))

        library_dir.mkdir(parents = True, exist_ok = True)
        for source, destination in staged:
            shutil.copyfile(str(source), str(destination))
            destination.chmod(0o644)

    # Refresh the loader cache and create any versioned SONAME links.
    subprocess.run(["ldconfig"], check = True)


def main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--library-dir", type = Path, default = Path("/usr/lib"))
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error("The pinned CI libraries require Linux x86_64")
    install_shared_libraries(args.library_dir)


if __name__ == "__main__":
    main()
