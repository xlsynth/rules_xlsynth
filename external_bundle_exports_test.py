import os
from pathlib import Path
import unittest

from python.runfiles import runfiles


class ExternalBundleExportsTest(unittest.TestCase):
    def test_stdlib_target_is_a_single_directory_runfile(self):
        runfiles_lookup = runfiles.Create()
        workspace = os.environ["TEST_WORKSPACE"]

        location_file = Path(runfiles_lookup.Rlocation("{}/stdlib_location.txt".format(workspace)))
        self.assertTrue(location_file.is_file())
        self.assertEqual(Path(location_file.read_text(encoding = "utf-8").strip()).name, "dslx_stdlib")

        stdlib_dir = Path(runfiles_lookup.Rlocation("rules_xlsynth_selftest_xls/dslx_stdlib"))
        self.assertTrue(stdlib_dir.is_dir())
        self.assertTrue(any(stdlib_dir.glob("*.x")))

    def test_repo_named_alias_exposes_bundle_runfiles(self):
        runfiles_lookup = runfiles.Create()
        workspace = os.environ["TEST_WORKSPACE"]

        locations_file = Path(runfiles_lookup.Rlocation("{}/bundle_alias_locations.txt".format(workspace)))
        self.assertTrue(locations_file.is_file())

        locations = locations_file.read_text(encoding = "utf-8").split()
        self.assertTrue(any(Path(path).name == "xlsynth-driver" for path in locations))
        self.assertTrue(any(Path(path).name == "libxls_patched.dylib" for path in locations))


if __name__ == "__main__":
    unittest.main()
