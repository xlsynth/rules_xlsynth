# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import env_helpers


class EnvHelpersTest(unittest.TestCase):

    def _invoke_quickcheck(self, report, returncode = 0, top = "", import_paths = (), passthrough = (), typecheck_returncode = 0):
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
            result = {}

            def fake_driver(args):
                result["driver_args"] = args
                output_index = args.passthrough.index("--output_json") + 1
                output_path = Path(args.passthrough[output_index])
                self.assertFalse(output_path.exists())
                if report is not None:
                    output_path.write_text(
                        report if isinstance(report, str) else json.dumps(report),
                        encoding = "utf-8",
                    )
                return returncode

            argv = [
                "xlsynth_runner", "quickcheck", "--driver_path", "xlsynth-driver",
                "--toolchain", str(toolchain), "--dslx_input_file", "proofs.x",
                "--runtime_library_path", "runtime", "--top", top,
            ] + list(passthrough)
            with mock.patch.dict(os.environ, {
                "XML_OUTPUT_FILE": str(xml_path),
                "RUNFILES_DIR": str(runfiles_root),
            }):
                with mock.patch.object(env_helpers, "_tool", return_value = typecheck_returncode) as typecheck:
                    with mock.patch.object(env_helpers, "_driver", side_effect = fake_driver):
                        result["exit_code"] = env_helpers.main(argv)
                    result["typecheck_args"] = typecheck.call_args[0][0]
            result["xml"] = ET.parse(str(xml_path)).getroot()
            result["stdlib"] = str(stdlib)
            return result

    def test_quickcheck_uses_bitwuzla_and_preserves_full_match_and_import_paths(self):
        report = {
            "success": True,
            "tests": [{"name": "qc_first", "success": True, "time_micros": 1250, "counterexample": None}],
        }
        result = self._invoke_quickcheck(
            report, top = "qc_first|qc_second", import_paths = ("first root", "second/root"),
        )
        self.assertEqual(result["exit_code"], 0)
        args = result["driver_args"]
        self.assertEqual(args.subcommand, "prove-quickcheck")
        self.assertEqual(args.driver_path, "xlsynth-driver")
        self.assertEqual(args.runtime_library_path, "runtime")
        self.assertEqual(result["typecheck_args"].tool, "typecheck_main")
        self.assertEqual(result["typecheck_args"].toolchain, args.toolchain)
        self.assertEqual(result["typecheck_args"].passthrough, ["proofs.x", "--output_path=" + os.devnull])
        self.assertEqual(args.passthrough[:-2], [
            "--dslx_input_file", "proofs.x",
            "--solver", "bitwuzla",
            "--assertion-semantics", "never",
            "--dslx_stdlib_path", result["stdlib"],
            "--dslx_path", "first root;second/root",
            "--test_filter", "^(?:qc_first|qc_second)$",
        ])
        self.assertEqual(args.passthrough[-2], "--output_json")
        suite = result["xml"].find("testsuite")
        self.assertEqual(suite.attrib, {
            "name": "proofs", "tests": "1", "failures": "0", "errors": "0", "time": "0.001250",
        })
        self.assertEqual(suite.find("testcase").attrib, {
            "name": "qc_first", "classname": "proofs", "file": "proofs.x", "time": "0.001250",
        })

    def test_quickcheck_without_top_proves_all_properties(self):
        report = {
            "success": True,
            "tests": [
                {"name": "qc_first", "success": True, "time_micros": 0},
                {"name": "qc_second", "success": True, "time_micros": 1000000},
            ],
        }
        result = self._invoke_quickcheck(report)
        self.assertEqual(result["exit_code"], 0)
        self.assertNotIn("--test_filter", result["driver_args"].passthrough)
        self.assertEqual(
            [case.get("name") for case in result["xml"].findall("testsuite/testcase")],
            ["qc_first", "qc_second"],
        )

    def test_quickcheck_failure_keeps_counterexample_and_exit_status(self):
        counterexample = 'inputs: [x = 0], output: false <assertion "failed">'
        report = {
            "success": False,
            "tests": [
                {"name": "qc_pass", "success": True, "time_micros": 4},
                {"name": "qc_fail", "success": False, "time_micros": 8, "counterexample": counterexample},
            ],
        }
        result = self._invoke_quickcheck(report, returncode = 1)
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["xml"].find("testsuite").get("failures"), "1")
        self.assertEqual(result["xml"].find("testsuite/testcase/failure").text, counterexample)
        self.assertEqual(result["xml"].find("testsuite").get("errors"), "0")

    def test_quickcheck_rejects_invalid_or_empty_report_even_if_driver_exits_zero(self):
        good_test = {"name": "qc_pass", "success": True, "time_micros": 1}
        reports = [
            None, "not json", [], {}, {"success": "true", "tests": [good_test]},
            {"success": True, "tests": []},
            {"success": True, "tests": None},
            {"success": True, "tests": [good_test, good_test]},
            {"success": False, "tests": [good_test]},
        ]
        for override in [
            {"name": ""}, {"success": "true"}, {"time_micros": -1},
            {"time_micros": True}, {"counterexample": 123},
        ]:
            test = dict(good_test)
            test.update(override)
            reports.append({"success": True, "tests": [test]})
        for report in reports:
            with self.subTest(report = report):
                result = self._invoke_quickcheck(report)
                self.assertNotEqual(result["exit_code"], 0)
                self.assertIsNotNone(result["xml"].find("testsuite/testcase/error"))

    def test_quickcheck_failure_report_cannot_be_overridden_by_zero_exit(self):
        result = self._invoke_quickcheck({
            "success": False,
            "tests": [{"name": "qc_fail", "success": False, "time_micros": 0}],
        })
        self.assertEqual(result["exit_code"], 1)
        self.assertIsNotNone(result["xml"].find("testsuite/testcase/failure"))

    def test_quickcheck_success_report_cannot_override_driver_error(self):
        result = self._invoke_quickcheck({
            "success": True,
            "tests": [{"name": "qc_pass", "success": True, "time_micros": 0}],
        }, returncode = 2)
        self.assertNotEqual(result["exit_code"], 0)
        self.assertIsNotNone(result["xml"].find("testsuite/testcase/error"))

    def test_quickcheck_does_not_prove_when_typechecking_fails(self):
        result = self._invoke_quickcheck(None, typecheck_returncode = 1)
        self.assertEqual(result["exit_code"], 1)
        self.assertNotIn("driver_args", result)
        self.assertIn("DSLX typechecking failed", result["xml"].find("testsuite/testcase/error").text)

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
