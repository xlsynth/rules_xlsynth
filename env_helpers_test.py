# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import env_helpers


class EnvHelpersTest(unittest.TestCase):

    def _invoke_quickcheck(self, returncode = 0, top = "", import_paths = (), passthrough = (), typecheck_returncode = 0, bazel_test = True):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runfiles_root = tmp_path / "runfiles"
            stdlib = runfiles_root / "+xls+runtime" / "stdlib"
            stdlib.mkdir(parents = True)
            toolchain = tmp_path / "toolchain.toml"
            toolchain.write_text(
                '[toolchain.dslx]\n'
                'dslx_stdlib_path = "external/+xls+runtime/stdlib"\n'
                'dslx_path = ' + json.dumps(list(import_paths)) + '\n',
                encoding = "utf-8",
            )
            xml_path = tmp_path / "test.xml"
            output_dir = tmp_path / "test outputs"
            output_dir.mkdir()
            argv = [
                "xlsynth_runner", "quickcheck", "--driver_path", "xlsynth-driver",
                "--toolchain", str(toolchain), "--dslx_input_file", "proofs.x",
                "--runtime_library_path", "runtime", "--top", top,
            ] + list(passthrough)
            with mock.patch.dict(os.environ, {
                "XML_OUTPUT_FILE": str(xml_path),
                "TEST_UNDECLARED_OUTPUTS_DIR": str(output_dir) if bazel_test else "",
                "RUNFILES_DIR": str(runfiles_root),
            }):
                with mock.patch.object(env_helpers, "_tool", return_value = typecheck_returncode) as typecheck:
                    with mock.patch.object(env_helpers, "_driver", return_value = returncode) as driver:
                        exit_code = env_helpers.main(argv)
            # Leave XML generation to Bazel, for both successes and failures.
            self.assertFalse(xml_path.exists())
            return {
                "exit_code": exit_code,
                "driver_args": driver.call_args[0][0] if driver.called else None,
                "typecheck_args": typecheck.call_args[0][0],
                "stdlib": str(stdlib),
                "report_path": str(output_dir / "quickcheck.json"),
            }

    def test_quickcheck_uses_bitwuzla_and_preserves_full_match_and_import_paths(self):
        result = self._invoke_quickcheck(
            top = "qc_first|qc_second", import_paths = ("first root", "second/root"),
        )
        self.assertEqual(result["exit_code"], 0)
        args = result["driver_args"]
        self.assertEqual(args.subcommand, "prove-quickcheck")
        self.assertEqual(args.driver_path, "xlsynth-driver")
        self.assertEqual(args.runtime_library_path, "runtime")
        self.assertEqual(result["typecheck_args"].tool, "typecheck_main")
        self.assertEqual(result["typecheck_args"].toolchain, args.toolchain)
        self.assertEqual(result["typecheck_args"].passthrough, ["proofs.x", "--output_path=" + os.devnull])
        self.assertEqual(args.passthrough, [
            "--dslx_input_file", "proofs.x",
            "--solver", "bitwuzla",
            "--assertion-semantics", "never",
            "--dslx_stdlib_path", result["stdlib"],
            "--dslx_path", "first root;second/root",
            "--test_filter", "^(?:qc_first|qc_second)$",
            "--output_json", result["report_path"],
        ])

    def test_quickcheck_without_top_does_not_filter(self):
        result = self._invoke_quickcheck()
        self.assertEqual(result["exit_code"], 0)
        self.assertNotIn("--test_filter", result["driver_args"].passthrough)

    def test_quickcheck_preserves_driver_exit_status(self):
        for returncode in (0, 1, 2):
            with self.subTest(returncode = returncode):
                result = self._invoke_quickcheck(returncode = returncode)
                self.assertEqual(result["exit_code"], returncode)

    def test_quickcheck_outside_bazel_does_not_request_a_report(self):
        result = self._invoke_quickcheck(bazel_test = False, passthrough = ["--opt=false"])
        self.assertEqual(result["exit_code"], 0)
        self.assertNotIn("--output_json", result["driver_args"].passthrough)
        self.assertEqual(result["driver_args"].passthrough[-1], "--opt=false")

    def test_quickcheck_does_not_prove_when_typechecking_fails(self):
        for returncode in (1, 2):
            with self.subTest(returncode = returncode):
                result = self._invoke_quickcheck(typecheck_returncode = returncode)
                self.assertEqual(result["exit_code"], returncode)
                self.assertIsNone(result["driver_args"])

    def test_driver_resolves_runfiles_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runfiles_root = tmp_path / "runfiles"
            driver_path = runfiles_root / "+xls+rules_xlsynth_selftest_xls_toolchain" / "xlsynth-driver"
            driver_path.parent.mkdir(parents = True)
            driver_path.write_text("#!/bin/sh\n", encoding = "utf-8")
            toolchain_path = tmp_path / "toolchain.toml"
            toolchain_path.write_text("[toolchain]\n", encoding = "utf-8")

            argv = mock.Mock(
                driver_path = "external/+xls+rules_xlsynth_selftest_xls_toolchain/xlsynth-driver",
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
            tools_path = runfiles_root / "+xls+rules_xlsynth_selftest_xls_runtime" / "tools"
            tools_path.mkdir(parents = True)
            toolchain_path = tmp_path / "toolchain.toml"
            toolchain_path.write_text(
                "[toolchain]\n"
                "tool_path = \"external/+xls+rules_xlsynth_selftest_xls_runtime/tools\"\n",
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
