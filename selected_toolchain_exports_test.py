# SPDX-License-Identifier: Apache-2.0

"""Tests the public, opt-in selected DSLX toolchain metadata outputs."""

import json
import os
from pathlib import Path
import unittest

from python.runfiles import runfiles


class SelectedToolchainExportsTest(unittest.TestCase):
    """Validates the public JSON outputs consumed outside Bazel analysis."""

    def read_metadata(self, relative_path):
        """Reads a requested metadata artifact through Bazel's runfiles contract."""
        workspace = os.environ["TEST_WORKSPACE"]
        path = runfiles.Create().Rlocation("{}/{}".format(workspace, relative_path))
        return json.loads(Path(path).read_text(encoding = "utf-8"))

    # Verifies: Default metadata contains separate canonical XLS/XLSynth pins.
    # Catches: Missing schema data or conflated producer release versions.
    def test_default_library_exposes_canonical_independent_producer_pins(self):
        metadata = self.read_metadata("sample/selected_toolchain_test_default_library.selected_toolchain.json")

        self.assertEqual(
            metadata,
            {
                "schema_version": 1,
                "xls_pin": {"kind": "release_tag", "value": "v0.40.0"},
                "xlsynth_crate_pin": {"kind": "release_tag", "value": "v0.36.0"},
            },
        )

    # Verifies: Metadata reflects the producer versions of a library override.
    # Catches: Reporting a repository default for an explicitly overridden target.
    def test_explicit_library_override_exposes_its_own_producer_pins(self):
        metadata = self.read_metadata("sample/selected_toolchain_test_override_library.selected_toolchain.json")

        self.assertEqual(metadata["xls_pin"], {"kind": "release_tag", "value": "v0.37.0"})
        self.assertEqual(metadata["xlsynth_crate_pin"], {"kind": "release_tag", "value": "v0.32.0"})

    # Verifies: JSON distinguishes and canonicalizes Git-revision producer pins.
    # Catches: Emitting a release tag or uppercase revision for a Git toolchain.
    def test_git_revisions_are_distinguished_and_normalized(self):
        metadata = self.read_metadata("sample/selected_toolchain_test_git_library.selected_toolchain.json")
        expected_xls_pin = {
            "kind": "git_revision",
            "value": "abcdef0123456789abcdef0123456789abcdef01",
        }
        expected_driver_pin = {
            "kind": "git_revision",
            "value": "1234567890abcdef1234567890abcdef12345678",
        }

        self.assertEqual(metadata["xls_pin"], expected_xls_pin)
        self.assertEqual(metadata["xlsynth_crate_pin"], expected_driver_pin)

    # Verifies: A release-pinned XLS producer can pair with a Git-pinned driver.
    # Catches: Conflating independent producer identities or their representations.
    def test_release_and_git_producer_pins_can_be_mixed(self):
        metadata = self.read_metadata("sample/selected_toolchain_test_mixed_library.selected_toolchain.json")

        self.assertEqual(metadata["xls_pin"], {"kind": "release_tag", "value": "v0.40.0"})
        self.assertEqual(
            metadata["xlsynth_crate_pin"],
            {"kind": "git_revision", "value": "1234567890abcdef1234567890abcdef12345678"},
        )

    # Verifies: Local versionless toolchains report missing producer pins as null.
    # Catches: Fabricated identity data or rejected local toolchain bundles.
    def test_versionless_bundle_preserves_explicitly_missing_pins(self):
        metadata = self.read_metadata("sample/selected_toolchain_test_unpinned_library.selected_toolchain.json")

        self.assertIsNone(metadata["xls_pin"])
        self.assertIsNone(metadata["xlsynth_crate_pin"])

    # Verifies: Preexisting external bundle shapes remain usable without new fields.
    # Catches: Requiring producer pins on public providers created before this feature.
    def test_legacy_bundle_without_producer_fields_reports_missing_pins(self):
        metadata = self.read_metadata("sample/selected_toolchain_test_legacy_library.selected_toolchain.json")

        self.assertIsNone(metadata["xls_pin"])
        self.assertIsNone(metadata["xlsynth_crate_pin"])

    # Verifies: Externally supplied producer structs are normalized before export.
    # Catches: Raw release or Git inputs bypassing the canonical producer parser.
    def test_external_bundle_producer_fields_are_canonicalized(self):
        metadata = self.read_metadata("sample/selected_toolchain_test_external_library.selected_toolchain.json")

        self.assertEqual(metadata["xls_pin"], {"kind": "release_tag", "value": "v0.40.0"})
        self.assertEqual(
            metadata["xlsynth_crate_pin"],
            {"kind": "git_revision", "value": "1234567890abcdef1234567890abcdef12345678"},
        )


if __name__ == "__main__":
    unittest.main()
