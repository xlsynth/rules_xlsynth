#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materializes the declared files of an installed Lean distribution."""

import argparse
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


def materialize(manifest_path, output_root):
    with open(manifest_path) as source:
        manifest = json.load(source)
    entries = manifest["entries"]
    relative_paths = [entry["relative"] for entry in entries]
    required = {
        "bin/lean",
        "bin/cadical",
        "lib/lean/Init.olean",
        "src/lean/Init.lean",
    }
    missing = sorted(required.difference(relative_paths))
    if missing:
        raise ValueError(
            "installed Lean {} at {} is missing required files: {}".format(
                manifest["version"], manifest["installed_root"], ", ".join(missing)
            )
        )
    if len(relative_paths) != len(set(relative_paths)):
        raise ValueError("installed Lean manifest contains duplicate relative paths")

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        relative = Path(entry["relative"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid Lean installation path: {}".format(relative))
        source = Path(entry["source"])
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(destination))
        os.chmod(str(destination), stat.S_IMODE(source.stat().st_mode))

    lean = output_root / "bin" / "lean"
    for executable in (lean, output_root / "bin" / "cadical"):
        if not os.access(str(executable), os.X_OK):
            raise ValueError("installed Lean executable is not executable: {}".format(executable))
    result = subprocess.run(
        [str(lean), "--short-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("installed Lean version query failed: {}".format(result.stderr.strip()))
    actual = result.stdout.strip()
    if actual != manifest["version"]:
        raise ValueError(
            "installed Lean version mismatch: expected {}, got {}".format(
                manifest["version"], actual
            )
        )
    with open(str(output_root / "xlsynth-lean-installation.json"), "w") as output:
        json.dump({"version": actual}, output, sort_keys=True)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        materialize(args.manifest, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, "error: {}\n".format(error))


if __name__ == "__main__":
    main()
