# SPDX-License-Identifier: Apache-2.0

import pathlib
import subprocess
import sys
import tempfile
import unittest


class MakeEnvHelpersTest(unittest.TestCase):

    def test_generated_env_helpers_matches_checked_in_file(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parent
        generator = repo_root / "make_env_helpers.py"
        env_helpers_bzl = repo_root / "env_helpers.bzl"
        env_helpers_py = repo_root / "env_helpers.py"

        with tempfile.TemporaryDirectory() as tmp:
            output_path = pathlib.Path(tmp) / "env_helpers.bzl"
            subprocess.run(
                [
                    sys.executable,
                    str(generator),
                    "--output",
                    str(output_path),
                    "--source",
                    str(env_helpers_py),
                ],
                check=True,
            )

            generated = output_path.read_text()
            expected = env_helpers_bzl.read_text()

            self.assertEqual(
                generated,
                expected,
                "env_helpers.bzl is out of date; run `python make_env_helpers.py`",
            )


if __name__ == "__main__":
    unittest.main()
