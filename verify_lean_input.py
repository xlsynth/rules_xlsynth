#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verifies a proof input hash and writes the exact bytes used for target preparation."""

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path


def verify_input(source_path, expected_hash, output_path, metadata_path, side, kind):
    expected_hash = expected_hash.lower()
    if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise ValueError("{} hash must contain exactly 64 hexadecimal characters".format(side))
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if kind == "netlist" and source_path.name.endswith(".gz") else open
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="proof-input-verify-", dir=str(output_path.parent)) as temporary:
        candidate = Path(temporary) / "verified"
        with opener(str(source_path), "rb") as source, open(str(candidate), "wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
        actual_hash = digest.hexdigest()
        if actual_hash != expected_hash:
            message = "{} {} hash mismatch\nExpected: {}\nActual:   {}".format(
                side.upper(), kind, expected_hash, actual_hash
            )
            if kind == "IR":
                message += (
                    "\nThe {} IR changed. Recheck the proof against the new graph before updating {}_ir_sha256."
                ).format(side.upper(), side)
            raise ValueError(message)
        os.replace(str(candidate), str(output_path))
    with open(metadata_path, "w") as metadata:
        json.dump({"sha256": actual_hash, "side": side}, metadata, sort_keys=True)
        metadata.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--expected-hash", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--side", choices=("lhs", "rhs"), required=True)
    parser.add_argument("--kind", choices=("netlist", "IR"), required=True)
    args = parser.parse_args()
    try:
        verify_input(args.input, args.expected_hash, args.output, args.metadata, args.side, args.kind)
    except (OSError, ValueError, EOFError) as error:
        parser.exit(1, "error: {}\n".format(error))


if __name__ == "__main__":
    main()
