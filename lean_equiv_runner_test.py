# SPDX-License-Identifier: Apache-2.0
"""Tests the IR proof driver's audit contract at the Bazel runner boundary."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netlist_lean_equiv_runner import run


class IrAuditTest(unittest.TestCase):
    def check_report(self, allow_native_checks, fields, accepted):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Proof.lean").touch()
            config = {
                "allow_native_checks": allow_native_checks,
                "checker": "ir-fn-lean-check",
                "driver": directory,
                "lean_root": directory,
                "lean_version": "test",
                "proof": {"relative": "Proof.lean", "runfile": "Proof.lean"},
                "proof_srcs": [],
                "proof_theorem": "equivalent",
                "target": directory,
                "toolchain": directory,
            }

            def driver(command, **kwargs):
                if "--version" in command:
                    return subprocess.CompletedProcess(command, 0, "test driver", "")
                self.assertEqual("--reject-native-checks" in command, not allow_native_checks)
                report = {"audit_performed": True, "status": "accepted_by_lean"}
                report.update(fields)
                path = Path(command[command.index("--output-json") + 1])
                path.write_text(json.dumps(report))
                return subprocess.CompletedProcess(command, 0, "", "")

            env = {"RUNFILES_DIR": directory, "TEST_UNDECLARED_OUTPUTS_DIR": directory}
            with patch.dict(os.environ, env), patch("subprocess.run", side_effect=driver):
                if accepted:
                    self.assertEqual(run(config), 0)
                else:
                    with self.assertRaisesRegex(RuntimeError, "native_checks_replayed"):
                        run(config)
            report = json.loads((root / "ir_fn_lean_equiv.json").read_text())
            self.assertEqual(report["status"], "accepted_by_lean" if accepted else "failed")
            return report

    def test_default_reports_count_and_accepts_older_drivers(self):
        self.assertNotIn("native_checks_replayed", self.check_report(True, {}, True))
        report = self.check_report(True, {"native_checks_replayed": 2}, True)
        self.assertEqual(report["native_checks_replayed"], 2)

    def test_strict_requires_an_explicit_zero(self):
        report = self.check_report(False, {"native_checks_replayed": 0}, True)
        self.assertEqual(report["native_checks_replayed"], 0)
        self.check_report(False, {"native_checks_replayed": 2}, False)
        self.check_report(False, {}, False)

    def test_rejects_malformed_counts(self):
        for allow in (False, True):
            for count in (False, -1, "0"):
                with self.subTest(allow=allow, count=count):
                    self.check_report(allow, {"native_checks_replayed": count}, False)


if __name__ == "__main__":
    unittest.main()
