#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verifies a netlist content hash and writes the exact bytes to be converted."""

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path


def verify_netlist(source_path, expected_hash, output_path, metadata_path, side):
    expected_hash = expected_hash.lower()
    if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise ValueError("{} hash must contain exactly 64 hexadecimal characters".format(side))
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if source_path.name.endswith(".gz") else open
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="netlist-verify-", dir=str(output_path.parent)) as temporary:
        candidate = Path(temporary) / "verified.gv"
        with opener(str(source_path), "rb") as source, open(str(candidate), "wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
        actual_hash = digest.hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                "{} netlist hash mismatch\nExpected: {}\nActual:   {}".format(
                    side.upper(), expected_hash, actual_hash
                )
            )
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
    args = parser.parse_args()
    try:
        verify_netlist(args.input, args.expected_hash, args.output, args.metadata, args.side)
    except (OSError, ValueError, EOFError) as error:
        parser.exit(1, "error: {}\n".format(error))


if __name__ == "__main__":
    main()
