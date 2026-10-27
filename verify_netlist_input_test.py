#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_netlist_input import verify_netlist


class VerifyNetlistInputTest(unittest.TestCase):
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
                verify_netlist(source, digest.upper(), verified, metadata, "lhs")
                self.assertEqual(verified.read_bytes(), contents)
                self.assertEqual(json.loads(metadata.read_text()), {"sha256": digest, "side": "lhs"})

    def test_mismatch_does_not_publish_verified_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "design.gv"
            source.write_text("module changed; endmodule\n")
            output = root / "verified.gv"
            metadata = root / "metadata.json"
            with self.assertRaisesRegex(ValueError, "RHS netlist hash mismatch"):
                verify_netlist(source, "0" * 64, output, metadata, "rhs")
            self.assertFalse(output.exists())
            self.assertFalse(metadata.exists())


if __name__ == "__main__":
    unittest.main()
