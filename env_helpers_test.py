# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import env_helpers


class EnvHelpersTest(unittest.TestCase):

    def test_driver_resolves_runfiles_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runfiles_root = tmp_path / "runfiles"
            driver_path = runfiles_root / "_main" / "external" / "+xls+rules_xlsynth_selftest_xls" / "xlsynth-driver"
            driver_path.parent.mkdir(parents = True)
            driver_path.write_text("#!/bin/sh\n", encoding = "utf-8")

            argv = mock.Mock(
                driver_path = "external/+xls+rules_xlsynth_selftest_xls/xlsynth-driver",
                toolchain = "toolchain.toml",
                subcommand = "--version",
                passthrough = [],
                runtime_library_path = "",
                stdout_path = "",
            )

            captured = {}

            def fake_run(cmd, check = False, env = None, stdout = None):
                captured["cmd"] = list(cmd)

                class Result:
                    returncode = 0

                return Result()

            with mock.patch.dict(os.environ, {"RUNFILES_DIR": str(runfiles_root)}, clear = False):
                with mock.patch.object(env_helpers.subprocess, "run", side_effect = fake_run):
                    self.assertEqual(env_helpers._driver(argv), 0)

            self.assertEqual(captured["cmd"][0], str(driver_path))


if __name__ == "__main__":
    unittest.main()
