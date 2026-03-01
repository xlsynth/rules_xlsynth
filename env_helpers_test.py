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
            driver_path = runfiles_root / "+xls+rules_xlsynth_selftest_xls" / "xlsynth-driver"
            driver_path.parent.mkdir(parents = True)
            driver_path.write_text("#!/bin/sh\n", encoding = "utf-8")
            toolchain_path = tmp_path / "toolchain.toml"
            toolchain_path.write_text("[toolchain]\n", encoding = "utf-8")

            argv = mock.Mock(
                driver_path = "external/+xls+rules_xlsynth_selftest_xls/xlsynth-driver",
                toolchain = str(toolchain_path),
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

    def test_driver_exports_xlsynth_tools_from_toolchain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runfiles_root = tmp_path / "runfiles"
            tools_path = runfiles_root / "+xls+rules_xlsynth_selftest_xls" / "tools"
            tools_path.mkdir(parents = True)
            toolchain_path = tmp_path / "toolchain.toml"
            toolchain_path.write_text(
                "[toolchain]\n"
                "tool_path = \"external/+xls+rules_xlsynth_selftest_xls/tools\"\n",
                encoding = "utf-8",
            )

            argv = mock.Mock(
                driver_path = "/tmp/xlsynth-driver",
                toolchain = str(toolchain_path),
                subcommand = "ir-equiv",
                passthrough = [],
                runtime_library_path = "",
                stdout_path = "",
            )

            captured = {}

            def fake_run(cmd, check = False, env = None, stdout = None):
                captured["env"] = dict(env)

                class Result:
                    returncode = 0

                return Result()

            with mock.patch.dict(os.environ, {"RUNFILES_DIR": str(runfiles_root)}, clear = False):
                with mock.patch.object(env_helpers.subprocess, "run", side_effect = fake_run):
                    self.assertEqual(env_helpers._driver(argv), 0)

            self.assertEqual(captured["env"]["XLSYNTH_TOOLS"], str(tools_path))

    def test_run_subprocess_uses_darwin_runtime_library_env_var(self) -> None:
        captured = {}

        def fake_run(cmd, check = False, env = None, stdout = None):
            captured["env"] = dict(env)

            class Result:
                returncode = 0

            return Result()

        with mock.patch.object(env_helpers.subprocess, "run", side_effect = fake_run):
            self.assertEqual(
                env_helpers._run_subprocess(
                    ["dummy-tool"],
                    runtime_library_path = "/tmp/runtime",
                    stdout_path = "",
                    sys_platform = "darwin",
                ),
                0,
            )

        self.assertEqual(captured["env"]["DYLD_LIBRARY_PATH"], "/tmp/runtime")
        self.assertNotIn("LD_LIBRARY_PATH", captured["env"])

    def test_dslx_fmt_does_not_receive_stdlib_flag(self) -> None:
        toolchain_data = {
            "toolchain": {
                "dslx": {
                    "dslx_stdlib_path": "/tmp/stdlib",
                },
            },
        }

        self.assertEqual(
            env_helpers._build_extra_args_for_tool("dslx_fmt", toolchain_data),
            [],
        )


if __name__ == "__main__":
    unittest.main()
