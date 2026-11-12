#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bazel test runner for Lean proofs of XLS IR function equivalence."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


CONFIG_RUNFILE = "@CONFIG_RUNFILE@"


def resolve_runfile(logical_path):
    roots = [os.environ.get("RUNFILES_DIR"), os.environ.get("TEST_SRCDIR"), sys.argv[0] + ".runfiles"]
    for root in roots:
        if root:
            candidate = os.path.join(root, logical_path)
            if os.path.exists(candidate):
                return os.path.abspath(candidate)
    manifest_path = os.environ.get("RUNFILES_MANIFEST_FILE")
    if manifest_path:
        with open(manifest_path) as manifest:
            for line in manifest:
                key, separator, value = line.rstrip("\n").partition(" ")
                if key == logical_path:
                    return value if separator else key
    raise FileNotFoundError("runfile is unavailable: {}".format(logical_path))


def stage_proof_file(item, root):
    path = root / item["relative"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(resolve_runfile(item["runfile"]))
    return str(path)


def run(config):
    started = time.monotonic()
    driver = resolve_runfile(config["driver"])
    lean_root = Path(resolve_runfile(config["lean_root"]))
    environment = os.environ.copy()
    runtime_library = config.get("runtime_library")
    if runtime_library:
        runtime_directory = str(Path(resolve_runfile(runtime_library)).parent)
        variable = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        existing = environment.get(variable)
        environment[variable] = runtime_directory + (os.pathsep + existing if existing else "")

    reject_native_checks = not config["allow_native_checks"]

    version = subprocess.run(
        [driver, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, env=environment, check=False,
    )
    if version.returncode != 0:
        raise RuntimeError("xlsynth-driver version query failed: {}".format(version.stderr))

    with tempfile.TemporaryDirectory(prefix="lean-equiv-", dir=os.environ.get("TEST_TMPDIR")) as temporary:
        temporary = Path(temporary)
        proof_root = temporary / "proof_inputs"
        child_report_path = temporary / "lean-result.json"
        command = [
            driver,
            "--toolchain=" + resolve_runfile(config["toolchain"]),
            "ir-fn-lean-check",
            "--target-dir", resolve_runfile(config["target"]),
            "--proof-root", str(proof_root),
            "--proof-theorem", config["proof_theorem"],
            "--proof", stage_proof_file(config["proof"], proof_root),
            "--lean", str(lean_root / "bin" / "lean"),
            "--work-dir", str(temporary / "work"),
            "--output-json", str(child_report_path),
        ]
        if reject_native_checks:
            command.append("--reject-native-checks")
        for item in config["proof_srcs"]:
            command.extend(["--proof-source", stage_proof_file(item, proof_root)])
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, env=environment, check=False,
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if child_report_path.exists():
            with open(str(child_report_path)) as source:
                lean_report = json.load(source)
        else:
            lean_report = {"status": "failed", "error": "driver did not write a Lean result report"}
        audited = lean_report.get("audit_performed") is True
        accepted = result.returncode == 0 and lean_report.get("status") == "accepted_by_lean" and audited
        report = {
            "audit_performed": audited,
            "driver_version": version.stdout.strip(),
            "elapsed_seconds": time.monotonic() - started,
            "lean": lean_report,
            "lean_version": config["lean_version"],
        }
        if "native_checks_replayed" in lean_report:
            count = lean_report["native_checks_replayed"]
            if type(count) is int and count >= 0:
                report["native_checks_replayed"] = count
            elif accepted:
                report["error"] = "expected a nonnegative integer for native_checks_replayed"
        if accepted and reject_native_checks and report.get("native_checks_replayed") != 0:
            report["error"] = "strict Lean audit requires the driver to report native_checks_replayed = 0"
        accepted = accepted and "error" not in report
        report["status"] = "accepted_by_lean" if accepted else "failed"
        output_directory = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
        if output_directory:
            Path(output_directory).mkdir(parents=True, exist_ok=True)
            with open(os.path.join(output_directory, "ir_fn_lean_equiv.json"), "w") as output:
                json.dump(report, output, indent=2, sort_keys=True)
                output.write("\n")
        if result.returncode == 0 and not accepted:
            raise RuntimeError(report.get("error", "driver succeeded without the required Lean proof or audit"))
        return result.returncode


def main():
    with open(resolve_runfile(CONFIG_RUNFILE)) as source:
        config = json.load(source)
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
