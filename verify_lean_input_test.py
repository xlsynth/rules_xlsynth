#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_lean_input import verify_input


class VerifyLeanInputTest(unittest.TestCase):
    def test_plain_and_gzip_inputs_produce_identical_verified_bytes(self):
        contents = b"module top(input a, output y); assign y = a; endmodule\n"
        digest = hashlib.sha256(contents).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plain = root / "design.gv"
            compressed = root / "design.gv.gz"
            plain.write_bytes(contents)
            with gzip.open(str(compressed), "wb") as output:
                output.write(contents)
            for index, source in enumerate((plain, compressed)):
                verified = root / ("verified{}.gv".format(index))
                metadata = root / ("metadata{}.json".format(index))
                verify_input(source, digest.upper(), verified, metadata, "lhs", "netlist")
                self.assertEqual(verified.read_bytes(), contents)
                self.assertEqual(json.loads(metadata.read_text()), {"sha256": digest, "side": "lhs"})

    def test_ir_verifies_exact_bytes_including_line_endings(self):
        contents = b"package example\r\n\r\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.ir"
            source.write_bytes(contents)
            verified = root / "verified.ir"
            metadata = root / "hash.json"
            digest = hashlib.sha256(contents).hexdigest()
            verify_input(source, digest, verified, metadata, "rhs", "IR")
            self.assertEqual(verified.read_bytes(), contents)
            self.assertEqual(json.loads(metadata.read_text()), {"sha256": digest, "side": "rhs"})

    def test_mismatch_names_the_pin_and_does_not_publish_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            source.write_bytes(b"changed\n")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            output = root / "verified"
            metadata = root / "hash.json"
            for kind, side, pin in (
                ("IR", "lhs", "lhs_ir_sha256"),
                ("IR", "rhs", "rhs_ir_sha256"),
                ("netlist", "lhs", "lhs_sha256"),
                ("netlist", "rhs", "rhs_sha256"),
            ):
                with self.subTest(kind=kind, side=side):
                    with self.assertRaises(ValueError) as failure:
                        verify_input(source, "0" * 64, output, metadata, side, kind)
                    self.assertEqual(
                        str(failure.exception),
                        "{} {} hash mismatch\nExpected: {}\nActual:   {}\n"
                        "Input has changed, regenerate the proof and update {}".format(
                            side.upper(), kind, "0" * 64, digest, pin
                        ),
                    )
                    self.assertFalse(output.exists())
                    self.assertFalse(metadata.exists())


if __name__ == "__main__":
    unittest.main()
