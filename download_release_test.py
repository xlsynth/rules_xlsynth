# SPDX-License-Identifier: Apache-2.0

import io
import tempfile
import unittest
from unittest import mock
from urllib import error as urlerror

import download_release


class _FakeResponse:
    def __init__(self, payload):
        self._buffer = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size = -1):
        return self._buffer.read(size)


class _FlakyResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size = -1):
        raise ConnectionResetError("stream reset")


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

    def test_copy_url_to_path_retries_after_stream_reset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination_path = f"{temp_dir}/artifact"
            with mock.patch.object(
                download_release,
                "request_with_retry",
                side_effect = [_FlakyResponse(), _FakeResponse(b"ok")],
            ):
                with mock.patch.object(download_release.time, "sleep"):
                    download_release.copy_url_to_path(
                        "https://example.invalid/artifact",
                        destination_path,
                        headers = {},
                        max_attempts = 2,
                    )
            with open(destination_path, "rb") as f:
                self.assertEqual(f.read(), b"ok")

    def test_copy_url_to_path_still_raises_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination_path = f"{temp_dir}/missing"
            not_found = urlerror.HTTPError(
                url = "https://example.invalid/missing",
                code = 404,
                msg = "not found",
                hdrs = None,
                fp = None,
            )
            with mock.patch.object(download_release, "request_with_retry", side_effect = not_found):
                with self.assertRaises(urlerror.HTTPError):
                    download_release.copy_url_to_path(
                        "https://example.invalid/missing",
                        destination_path,
                        headers = {},
                        max_attempts = 2,
                    )


if __name__ == "__main__":
    unittest.main()
