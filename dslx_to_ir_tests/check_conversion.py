#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

"""Reparse optimized packages and check fixture-specific structural facts.

The production optimizer already parses the raw artifact. These text probes run
only after XLS has validated both artifacts; they are not an IR parser or a
behavioral proc test, and do not depend on generated symbol spelling.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def require(pattern: str, text: str, description: str) -> None:
    if not re.search(pattern, text, re.MULTILINE):
        raise AssertionError(f"Missing {description}: {pattern!r}\n{text}")


def check_channels(text: str, payload: str) -> None:
    # XLS releases can represent external channels in package-level channel
    # declarations or in a proc's interface. Accept both representations.
    require(r"(?:^chan [^\n]*input[^\n]*" + payload + r"[^\n]*ops=receive_only|input:\s*" + payload + r"\s+in)", text, "input channel")
    require(r"(?:^chan [^\n]*output[^\n]*" + payload + r"[^\n]*ops=send_only|output:\s*" + payload + r"\s+out)", text, "output channel")


def check_fixture(fixture: str, raw: str, optimized: str) -> None:
    for text in [raw, optimized]:
        kind = "proc" if fixture in ("accumulator", "workers") else "fn"
        tops = re.findall(r"^top (fn|proc) ", text, re.MULTILINE)
        if tops != [kind]:
            raise AssertionError(f"Expected one top {kind}, got {tops}\n{text}")
        if fixture in ("accumulator", "workers"):
            payload = r"bits\[32\]" if fixture == "accumulator" else r"\(bits\[32\], bits\[1\]\)"
            check_channels(text, payload)
            require(r"= receive\(", text, "receive operation")
            require(r"= send\(", text, "send operation")
        elif fixture in ("narrow", "wide", "imports", "arithmetic"):
            width = {"narrow": 16, "wide": 32, "imports": 1, "arithmetic": 32}[fixture]
            require(r"^top fn [^\n]* -> bits\[" + str(width) + r"\]", text, "selected return type")
        elif fixture == "asserting":
            require(r"= assert\(", text, "assert operation")

    if fixture == "arithmetic":
        require(r"= add\(", raw, "raw addition")
        if re.search(r"= add\(", optimized):
            raise AssertionError("Optimizer failed to eliminate addition by zero")
        if "arithmetic_test" in raw:
            raise AssertionError("Converter included a test function")
    elif fixture == "accumulator":
        require(r"init=\{0\}", raw, "zero initial accumulator state")
    elif fixture == "workers":
        require(r"init=\{\(\)\}", raw, "empty tuple state")
        for increment in [3, 5]:
            require(r"= literal\(value=" + str(increment) + r"[,)]", raw, "specialized worker increment")
        if len(re.findall(r"= receive\(", raw)) < 2:
            raise AssertionError("Expected both spawned workers to be elaborated")


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("runner", "toolchain", "runtime-library-path", "raw", "optimized", "fixture"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as temp:
        # No --top override: parsing and optimization must honor the serialized
        # package entrypoint even when conversion generated a proc instance.
        subprocess.run([
            sys.executable, args.runner, "tool",
            "--toolchain", args.toolchain,
            "--runtime_library_path", args.runtime_library_path,
            "--stdout_path", str(Path(temp) / "validated.ir"),
            "opt_main", args.optimized,
        ], check=True)
    check_fixture(args.fixture, Path(args.raw).read_text(), Path(args.optimized).read_text())


if __name__ == "__main__":
    main()
