#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""End-to-end Bazel test using explicitly supplied XLS and Lean installations."""

import gzip
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


RULES_ROOT = Path(__file__).resolve().parent
FIXTURES = RULES_ROOT / "testdata" / "netlist_lean_equiv"
LEAN_VERSION = "4.34.1"


def quote(value):
    return json.dumps(str(value))


def target(name, rhs, rhs_hash, lhs_hash, lhs="@netlists//:lhs.gv", proof="Proof/Body.lean", extra=""):
    return """
netlist_lean_equiv_test(
    name = {name},
    lhs = {lhs},
    lhs_hash = {lhs_hash},
    rhs = {rhs},
    rhs_hash = {rhs_hash},
    liberty_proto = "cells.textproto",
    lhs_top = "top",
    rhs_top = "top",
    proof = {proof},
{extra}
)
""".format(name=quote(name), lhs=quote(lhs), lhs_hash=quote(lhs_hash), rhs=quote(rhs), rhs_hash=quote(rhs_hash), proof=quote(proof), extra=extra)


class NetlistLeanEquivIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = [
            "RULES_XLSYNTH_TEST_DRIVER",
            "RULES_XLSYNTH_TEST_XLS_ROOT",
            "RULES_XLSYNTH_TEST_LEAN_ROOT",
        ]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise unittest.SkipTest("set installed test paths: " + ", ".join(missing))
        cls.driver = Path(os.environ[required[0]]).resolve()
        cls.xls_root = Path(os.environ[required[1]]).resolve()
        cls.lean_root = Path(os.environ[required[2]]).resolve()
        cls.bazel = os.environ.get("RULES_XLSYNTH_TEST_BAZEL", "bazel")
        cls.startup_options = shlex.split(os.environ.get("RULES_XLSYNTH_TEST_BAZEL_STARTUP_OPTIONS", ""))

    def bazel_command(self, workspace, arguments, expected_success=True, expected_text=None):
        print("bazel " + " ".join(arguments), flush=True)
        result = subprocess.run(
            [self.bazel] + self.startup_options + arguments,
            cwd=str(workspace), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, check=False,
        )
        if expected_success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        if expected_text:
            self.assertIn(expected_text, result.stdout)
        return result.stdout

    def module_source(self, netlists, lean_prefix, lean_attributes=True):
        libxls = self.xls_root / ("libxls.dylib" if sys.platform == "darwin" else "libxls.so")
        lean = ""
        if lean_attributes:
            lean = "    lean_version = {},\n    installed_lean_root_prefix = {},\n".format(
                quote(LEAN_VERSION), quote(lean_prefix)
            )
        return """module(name = "netlist_lean_integration")
bazel_dep(name = "rules_xlsynth", version = "0.0.0")
local_path_override(module_name = "rules_xlsynth", path = {rules_root})
new_local_repository = use_repo_rule("@bazel_tools//tools/build_defs/repo:local.bzl", "new_local_repository")
new_local_repository(
    name = "netlists",
    path = {netlists},
    build_file_content = 'exports_files(["lhs.gv", "rhs.gv.gz", "rhs_bad.gv", "pipeline_lhs.gv", "pipeline_rhs.gv"])',
)
xls = use_extension("@rules_xlsynth//:extensions.bzl", "xls")
xls.toolchain(
    name = "local_xls",
    artifact_source = "local_paths",
    local_driver_path = {driver},
    local_tools_path = {xls_root},
    local_dslx_stdlib_path = {stdlib},
    local_libxls_path = {libxls},
{lean})
use_repo(xls, "local_xls_runtime", "local_xls_toolchain")
register_toolchains("@local_xls_toolchain//:all")
""".format(
            rules_root=quote(RULES_ROOT), netlists=quote(netlists), driver=quote(self.driver),
            xls_root=quote(self.xls_root), stdlib=quote(self.xls_root / "xls/dslx/stdlib"),
            libxls=quote(libxls), lean=lean,
        )

    def read_report(self, workspace, name):
        logs = Path(self.bazel_command(workspace, ["info", "bazel-testlogs"]).strip().splitlines()[-1])
        output_dir = logs / name / "test.outputs"
        direct = output_dir / "netlist_lean_equiv.json"
        if direct.exists():
            return json.loads(direct.read_text())
        with zipfile.ZipFile(str(output_dir / "outputs.zip")) as archive:
            return json.loads(archive.read("netlist_lean_equiv.json").decode())

    def test_complete_rule_and_configuration_failures(self):
        with tempfile.TemporaryDirectory(prefix="rules-xlsynth-lean-integration-") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            netlists = root / "netlists"
            netlists.mkdir()
            lhs = (FIXTURES / "lhs.gv").read_bytes()
            rhs = (FIXTURES / "rhs.gv").read_bytes()
            bad = (FIXTURES / "rhs_bad.gv").read_bytes()
            pipeline_lhs = (FIXTURES / "pipeline_lhs.gv").read_bytes()
            pipeline_rhs = (FIXTURES / "pipeline_rhs.gv").read_bytes()
            (netlists / "lhs.gv").write_bytes(lhs)
            (netlists / "rhs_bad.gv").write_bytes(bad)
            (netlists / "pipeline_lhs.gv").write_bytes(pipeline_lhs)
            (netlists / "pipeline_rhs.gv").write_bytes(pipeline_rhs)
            with gzip.open(str(netlists / "rhs.gv.gz"), "wb") as output:
                output.write(rhs)
            shutil.copyfile(str(FIXTURES / "cells.textproto"), str(workspace / "cells.textproto"))
            shutil.copyfile(str(FIXTURES / "boundaries.json"), str(workspace / "boundaries.json"))
            shutil.copytree(str(FIXTURES / "Proof"), str(workspace / "Proof"))
            lean_prefix = root / "lean"
            lean_prefix.mkdir()
            (lean_prefix / LEAN_VERSION).symlink_to(self.lean_root, target_is_directory=True)
            module = workspace / "MODULE.bazel"
            module.write_text(self.module_source(netlists, lean_prefix))
            lhs_hash = hashlib.sha256(lhs).hexdigest()
            rhs_hash = hashlib.sha256(rhs).hexdigest()
            bad_hash = hashlib.sha256(bad).hexdigest()
            pipeline_options = """    lhs_cone_boundary_file = "boundaries.json",
    rhs_cone_boundary_file = "boundaries.json",
    collapse_sequential = True,
    collapse_load_enable_feedback = True,"""
            helper_options = '    proof_srcs = ["Proof/Helpers/Proof.lean", "Proof/Helpers/Lemmas.lean"],'
            (workspace / "BUILD.bazel").write_text(
                'load("@rules_xlsynth//:rules.bzl", "netlist_lean_equiv_test")\n' +
                target("equivalent", "@netlists//:rhs.gv.gz", rhs_hash, lhs_hash) +
                target(
                    "with_helpers", "@netlists//:rhs.gv.gz", rhs_hash, lhs_hash,
                    proof="Proof/WithHelpers.lean", extra=helper_options,
                ) +
                target("bad_hash", "@netlists//:rhs.gv.gz", "0" * 64, lhs_hash) +
                target("different", "@netlists//:rhs_bad.gv", bad_hash, lhs_hash) +
                target(
                    "pipeline", "@netlists//:pipeline_rhs.gv", hashlib.sha256(pipeline_rhs).hexdigest(),
                    hashlib.sha256(pipeline_lhs).hexdigest(), lhs="@netlists//:pipeline_lhs.gv",
                    extra=pipeline_options,
                )
            )

            self.bazel_command(workspace, ["test", "//:equivalent", "//:pipeline", "//:with_helpers", "--test_output=errors", "--nocache_test_results"])
            report = self.read_report(workspace, "equivalent")
            self.assertEqual(report["status"], "accepted_by_lean")
            self.assertFalse(report["audit_performed"])
            self.assertEqual(report["netlist_sha256"], {"lhs": lhs_hash, "rhs": rhs_hash})
            self.assertEqual(self.read_report(workspace, "pipeline")["status"], "accepted_by_lean")
            self.assertEqual(self.read_report(workspace, "with_helpers")["status"], "accepted_by_lean")
            self.bazel_command(workspace, ["build", "//:equivalent", "--output_groups=lean_target"])
            target_root = workspace / "bazel-bin" / "equivalent.lean_target"
            for relative in ("Lhs.aag", "Rhs.aag", "Target.lean", "Check.lean"):
                self.assertTrue((target_root / relative).is_file(), relative)
            self.assertFalse((target_root / "Generated").exists())
            pipeline_header = (workspace / "bazel-bin/pipeline.lean_target/Lhs.aag").read_text().splitlines()[0].split()
            self.assertEqual(pipeline_header[4], "1")

            self.bazel_command(
                workspace, ["test", "//:bad_hash", "--test_output=errors"],
                expected_success=False, expected_text="RHS netlist hash mismatch",
            )
            self.bazel_command(
                workspace, ["test", "//:different", "--test_output=errors", "--nocache_test_results"],
                expected_success=False,
            )
            different_report = self.read_report(workspace, "different")
            self.assertEqual(different_report["status"], "failed")
            self.assertIn("Lean user proof compilation failed", different_report["lean"]["error"])
            self.assertIn("native_decide", different_report["lean"]["error"])

            module.write_text(self.module_source(netlists, lean_prefix, lean_attributes=False))
            self.bazel_command(
                workspace, ["build", "//:equivalent"], expected_success=False,
                expected_text="requires lean_version and installed_lean_root_prefix",
            )
            partial = self.module_source(netlists, lean_prefix).replace(
                "    installed_lean_root_prefix = {},\n".format(quote(lean_prefix)), ""
            )
            module.write_text(partial)
            self.bazel_command(
                workspace, ["build", "//:equivalent"], expected_success=False,
                expected_text="lean_version and installed_lean_root_prefix must be supplied together",
            )
            module.write_text(self.module_source(netlists, root / "missing-lean"))
            self.bazel_command(
                workspace, ["build", "//:equivalent"], expected_success=False,
                expected_text="missing required files",
            )


if __name__ == "__main__":
    unittest.main()
