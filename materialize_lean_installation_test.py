#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
import unittest
from pathlib import Path

from materialize_lean_installation import materialize


def fixture(root, reported_version="4.34.1"):
    contents = {
        "bin/lean": "#!/bin/sh\nprintf '%s\\n' '{}'\n".format(reported_version),
        "bin/cadical": "#!/bin/sh\nexit 0\n",
        "lib/lean/Init.olean": "fixture olean\n",
        "src/lean/Init.lean": "-- fixture source\n",
        "lib/lean/Std.olean": "fixture std\n",
    }
    entries = []
    for relative, content in contents.items():
        path = root / "installed" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if relative.startswith("bin/"):
            path.chmod(0o755)
        entries.append({"relative": relative, "source": str(path)})
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({
        "entries": entries,
        "source": str(root / "installed"),
        "version": "4.34.1",
    }))
    return manifest


class MaterializeLeanInstallationTest(unittest.TestCase):
    def test_preserves_layout_and_validates_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            materialize(fixture(root), output)
            self.assertTrue(os.access(str(output / "bin/lean"), os.X_OK))
            self.assertEqual((output / "lib/lean/Std.olean").read_text(), "fixture std\n")
            self.assertEqual(
                json.loads((output / "xlsynth-lean-installation.json").read_text()),
                {"version": "4.34.1"},
            )

    def test_rejects_missing_distribution_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = fixture(root)
            data = json.loads(manifest.read_text())
            data["entries"] = []
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "missing required files"):
                materialize(manifest, root / "output")

    def test_rejects_version_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "expected 4.34.1, got 4.35.0"):
                materialize(fixture(root, "4.35.0"), root / "output")


if __name__ == "__main__":
    unittest.main()
