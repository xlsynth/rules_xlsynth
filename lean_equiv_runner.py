#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bazel test runner for Lean proofs of XLS IR function and mapped-netlist equivalence."""

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
                line = line.rstrip("\n")
                if line.startswith(" "):
                    # Bazel escapes spaces only in the key, and backslashes and newlines in both paths.
                    key, _, value = line[1:].partition(" ")
                    key = key.replace(r"\s", " ").replace(r"\n", "\n").replace(r"\b", "\\")
                    value = value.replace(r"\n", "\n").replace(r"\b", "\\")
                else:
                    key, _, value = line.partition(" ")
                if key == logical_path:
                    return value or key
    raise FileNotFoundError("runfile is unavailable: {}".format(logical_path))


def stage_proof_file(item, root):
    path = root / item["relative"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(resolve_runfile(item["runfile"]))
    return str(path)


def verified_hashes(config, ir_function):
    hashes = {}
    for side in ("lhs", "rhs"):
        if ir_function and side + "_hash" not in config:
            continue
        with open(resolve_runfile(config[side + "_hash_metadata"])) as source:
            metadata = json.load(source)
        if metadata["side"] != side or metadata["sha256"] != config[side + "_hash"]:
            raise ValueError("{} verified hash metadata is inconsistent".format(side))
        hashes[side] = metadata["sha256"]
    return hashes


def check_audit(report, accepted, allow_native_checks):
    """Validate the required proof audit, including the strict-mode count."""
    lean_report = report["lean"]
    accepted = accepted and report["audit_performed"]
    if "native_checks_replayed" in lean_report:
        count = lean_report["native_checks_replayed"]
        if type(count) is int and count >= 0:
            report["native_checks_replayed"] = count
        elif accepted:
            report["error"] = "expected a nonnegative integer for native_checks_replayed"
    if accepted and not allow_native_checks and report.get("native_checks_replayed") != 0:
        report["error"] = "strict Lean audit requires the driver to report native_checks_replayed = 0"
    return accepted and "error" not in report


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

    check_command = config.get("check_command", "ir-fn-lean-check")
    if check_command not in ("ir-fn-lean-check", "g8r-lean-check"):
        raise ValueError("unknown Lean proof command: {}".format(check_command))
    ir_function = check_command == "ir-fn-lean-check"
    hashes = verified_hashes(config, ir_function)

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
            check_command,
            "--target-dir", resolve_runfile(config["target"]),
            "--proof-root", str(proof_root),
            "--proof", stage_proof_file(config["proof"], proof_root),
            "--proof-theorem", config["proof_theorem"],
            "--lean", str(lean_root / "bin" / "lean"),
            "--work-dir", str(temporary / "work"),
            "--output-json", str(child_report_path),
        ]
        if not config["allow_native_checks"]:
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
        accepted = result.returncode == 0 and lean_report.get("status") == "accepted_by_lean"
        report = {
            "audit_performed": lean_report.get("audit_performed") is True,
            "driver_version": version.stdout.strip(),
            "elapsed_seconds": time.monotonic() - started,
            "lean": lean_report,
            "lean_version": config["lean_version"],
        }
        accepted = check_audit(report, accepted, config["allow_native_checks"])
        if ir_function:
            if hashes:
                report["ir_sha256"] = hashes
            report_name = "ir_fn_lean_equiv.json"
        else:
            report["netlist_sha256"] = hashes
            report["extraction"] = config["extraction"]
            report_name = "netlist_lean_equiv.json"
        report["status"] = "accepted_by_lean" if accepted else "failed"
        output_directory = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
        if output_directory:
            Path(output_directory).mkdir(parents=True, exist_ok=True)
            with open(os.path.join(output_directory, report_name), "w") as output:
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
