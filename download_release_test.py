# SPDX-License-Identifier: Apache-2.0

import unittest

import download_release


class DownloadReleaseTest(unittest.TestCase):
    def test_binary_release_filename_keeps_platform_suffix(self):
        self.assertEqual(
            download_release.build_binary_release_filename("dslx_fmt", "arm64"),
            "dslx_fmt-arm64",
        )

    def test_dso_release_filename_is_not_double_suffixed(self):
        self.assertEqual(
            download_release.build_dso_release_filename("arm64", (0, 38, 0, 0)),
            "libxls-arm64.dylib.gz",
        )
        self.assertEqual(
            download_release.build_dso_release_filename("ubuntu2004", (0, 38, 0, 0)),
            "libxls-ubuntu2004.so.gz",
        )

    def test_old_release_dso_filename_is_not_gzipped(self):
        self.assertEqual(
            download_release.build_dso_release_filename("ubuntu2004", (0, 0, 218, 0)),
            "libxls-ubuntu2004.so",
        )

    def test_release_artifacts_mix_binary_and_dso_filenames(self):
        artifacts = download_release.build_release_artifacts("v0.38.0", "arm64", True)
        self.assertIn(("dslx_fmt-arm64", True), artifacts)
        self.assertIn(("libxls-arm64.dylib.gz", False), artifacts)


if __name__ == "__main__":
    unittest.main()
