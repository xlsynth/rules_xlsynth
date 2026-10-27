#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bazel test runner for a Lean proof body and generated equivalence target."""

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


def stage_proof_files(config, destination):
    paths = {}
    for item in [config["proof"]] + config["proof_srcs"]:
        target = destination / item["relative"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(resolve_runfile(item["runfile"]))
        paths[item["relative"]] = str(target)
    return paths


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

    hashes = {}
    for side in ("lhs", "rhs"):
        with open(resolve_runfile(config[side + "_hash_metadata"])) as source:
            metadata = json.load(source)
        if metadata["sha256"] != config[side + "_hash"]:
            raise ValueError("{} verified hash metadata is inconsistent".format(side))
        hashes[side] = metadata["sha256"]

    version = subprocess.run(
        [driver, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, env=environment, check=False,
    )
    if version.returncode != 0:
        raise RuntimeError("xlsynth-driver version query failed: {}".format(version.stderr))

    with tempfile.TemporaryDirectory(prefix="netlist-lean-equiv-", dir=os.environ.get("TEST_TMPDIR")) as temporary:
        temporary = Path(temporary)
        proof_root = temporary / "proof_inputs"
        proof_root.mkdir()
        staged = stage_proof_files(config, proof_root)
        child_report_path = temporary / "lean-result.json"
        command = [
            driver,
            "--toolchain=" + resolve_runfile(config["toolchain"]),
            "g8r-lean-check",
            "--target-dir", resolve_runfile(config["target"]),
            "--proof-root", str(proof_root),
            "--proof", staged[config["proof"]["relative"]],
            "--lean", str(lean_root / "bin" / "lean"),
            "--work-dir", str(temporary / "work"),
            "--output-json", str(child_report_path),
        ]
        for item in config["proof_srcs"]:
            command.extend(["--proof-source", staged[item["relative"]]])
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
        accepted = result.returncode == 0 and lean_report["status"] == "accepted_by_lean"
        report = {
            "audit_performed": False,
            "driver_version": version.stdout.strip(),
            "elapsed_seconds": time.monotonic() - started,
            "extraction": config["extraction"],
            "lean": lean_report,
            "lean_version": config["lean_version"],
            "netlist_sha256": hashes,
            "status": "accepted_by_lean" if accepted else "failed",
        }
        output_directory = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
        if output_directory:
            Path(output_directory).mkdir(parents=True, exist_ok=True)
            with open(os.path.join(output_directory, "netlist_lean_equiv.json"), "w") as output:
                json.dump(report, output, indent=2, sort_keys=True)
                output.write("\n")
        if result.returncode == 0 and not accepted:
            raise RuntimeError("driver succeeded without an accepted Lean result")
        return result.returncode


def main():
    with open(resolve_runfile(CONFIG_RUNFILE)) as source:
        config = json.load(source)
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
