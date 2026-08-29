# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import install_ci_bitwuzla


class InstallCiBitwuzlaTest(unittest.TestCase):
    def fake_download(self, release_url, filename, target_dir, max_attempts):
        (Path(target_dir) / filename).write_bytes(b"\x7fELF" + filename.encode("ascii"))

    def test_installs_verified_release_libraries_under_development_names(self):
        with tempfile.TemporaryDirectory() as tempdir:
            library_dir = Path(tempdir) / "lib"
            with mock.patch.object(
                install_ci_bitwuzla.download_release,
                "high_integrity_download",
                side_effect = self.fake_download,
            ) as download:
                with mock.patch.object(install_ci_bitwuzla.subprocess, "run") as run:
                    install_ci_bitwuzla.install_shared_libraries(library_dir)

            self.assertEqual(
                download.call_args_list,
                [
                    mock.call(
                        "https://github.com/xlsynth/boolector-build/releases/download/"
                        "bitwuzla-binaries-b29041fbbe6318cb4c19a6e11c7616efc4cb4d32",
                        "lib{}-rocky8.so".format(name),
                        mock.ANY,
                        max_attempts = 5,
                    )
                    for name in ("bitwuzla", "bitwuzlabb", "bitwuzlabv", "bitwuzlals", "cadical")
                ],
            )
            self.assertEqual(
                sorted(path.name for path in library_dir.iterdir()),
                ["libbitwuzla.so", "libbitwuzlabb.so", "libbitwuzlabv.so", "libbitwuzlals.so", "libcadical.so"],
            )
            for name in install_ci_bitwuzla.LIBRARIES:
                installed = library_dir / "lib{}.so".format(name)
                self.assertEqual(installed.read_bytes(), b"\x7fELF" + "lib{}-rocky8.so".format(name).encode("ascii"))
                self.assertEqual(installed.stat().st_mode & 0o777, 0o644)
            run.assert_called_once_with(["ldconfig"], check = True)

    def test_rejects_non_elf_before_installing_any_library(self):
        def download(release_url, filename, target_dir, max_attempts):
            self.fake_download(release_url, filename, target_dir, max_attempts)
            if filename == "libcadical-rocky8.so":
                (Path(target_dir) / filename).write_bytes(b"<html>error</html>")

        with tempfile.TemporaryDirectory() as tempdir:
            library_dir = Path(tempdir) / "lib"
            with mock.patch.object(install_ci_bitwuzla.download_release, "high_integrity_download", side_effect = download):
                with mock.patch.object(install_ci_bitwuzla.subprocess, "run") as run:
                    with self.assertRaisesRegex(ValueError, "Expected ELF shared library"):
                        install_ci_bitwuzla.install_shared_libraries(library_dir)
            self.assertFalse(library_dir.exists())
            run.assert_not_called()

    def test_checksum_failure_prevents_installation(self):
        def download(url, destination_path, headers, max_attempts):
            destination = Path(destination_path)
            if url.endswith(".sha256"):
                destination.write_text("0" * 64 + "  libbitwuzla-rocky8.so\n", encoding = "utf-8")
            else:
                destination.write_bytes(b"\x7fELFcorrupted library")

        with tempfile.TemporaryDirectory() as tempdir:
            library_dir = Path(tempdir) / "lib"
            with mock.patch.object(
                install_ci_bitwuzla.download_release,
                "copy_url_to_path",
                side_effect = download,
            ) as fetch:
                with mock.patch.object(install_ci_bitwuzla.subprocess, "run") as run:
                    with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                        install_ci_bitwuzla.install_shared_libraries(library_dir)
            self.assertEqual(
                [call[0][0] for call in fetch.call_args_list],
                [
                    install_ci_bitwuzla.RELEASE_URL + "/libbitwuzla-rocky8.so.sha256",
                    install_ci_bitwuzla.RELEASE_URL + "/libbitwuzla-rocky8.so",
                ],
            )
            self.assertFalse(library_dir.exists())
            run.assert_not_called()

    def test_loader_cache_failure_is_fatal(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with mock.patch.object(
                install_ci_bitwuzla.download_release,
                "high_integrity_download",
                side_effect = self.fake_download,
            ):
                with mock.patch.object(
                    install_ci_bitwuzla.subprocess,
                    "run",
                    side_effect = subprocess.CalledProcessError(1, ["ldconfig"]),
                ):
                    with self.assertRaises(subprocess.CalledProcessError):
                        install_ci_bitwuzla.install_shared_libraries(Path(tempdir) / "lib")


if __name__ == "__main__":
    unittest.main()
