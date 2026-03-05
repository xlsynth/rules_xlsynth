import os
from pathlib import Path
import unittest

from python.runfiles import runfiles


def expected_libxls_name():
    return "libxls.dylib" if os.uname().sysname == "Darwin" else "libxls.so"


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
        self.assertTrue(any(Path(path).name == "block_to_verilog_main" for path in locations))

    def test_xlsynth_sys_runtime_export_is_narrow(self):
        runfiles_lookup = runfiles.Create()
        workspace = os.environ["TEST_WORKSPACE"]

        locations_file = Path(
            runfiles_lookup.Rlocation("{}/xlsynth_sys_runtime_locations.txt".format(workspace)),
        )
        self.assertTrue(locations_file.is_file())

        locations = locations_file.read_text(encoding = "utf-8").split()
        basenames = [Path(path).name for path in locations]

        self.assertIn("dslx_stdlib", basenames)
        self.assertTrue(any(name.startswith("libxls") for name in basenames))
        self.assertFalse(any(name == "xlsynth-driver" for name in basenames))
        self.assertFalse(any(name == "block_to_verilog_main" for name in basenames))

    def test_xlsynth_sys_artifact_config_export_points_at_config_file(self):
        runfiles_lookup = runfiles.Create()
        workspace = os.environ["TEST_WORKSPACE"]

        location_file = Path(
            runfiles_lookup.Rlocation("{}/xlsynth_sys_artifact_config_location.txt".format(workspace)),
        )
        self.assertTrue(location_file.is_file())
        self.assertEqual(
            Path(location_file.read_text(encoding = "utf-8").strip()).name,
            "xlsynth_artifact_config.toml",
        )

    def test_xlsynth_sys_artifact_config_export_is_self_contained(self):
        runfiles_lookup = runfiles.Create()
        config_path = Path(
            runfiles_lookup.Rlocation(
                "rules_xlsynth_selftest_xls/artifact_config/xlsynth_artifact_config.toml",
            ),
        )
        self.assertTrue(config_path.is_file())

        config_lines = dict(
            line.split(" = ", 1)
            for line in config_path.read_text(encoding = "utf-8").splitlines()
            if line
        )
        expected_dso_name = expected_libxls_name()
        self.assertEqual(config_lines["dso_path"].strip('"'), expected_dso_name)
        self.assertEqual(config_lines["dslx_stdlib_path"].strip('"'), "dslx_stdlib")
        self.assertTrue((config_path.parent / expected_dso_name).is_file())
        self.assertTrue((config_path.parent / "dslx_stdlib").is_dir())

    def test_xlsynth_sys_dep_export_packages_runtime_payload(self):
        runfiles_lookup = runfiles.Create()
        workspace = os.environ["TEST_WORKSPACE"]

        locations_file = Path(
            runfiles_lookup.Rlocation("{}/xlsynth_sys_dep_locations.txt".format(workspace)),
        )
        self.assertTrue(locations_file.is_file())

        basenames = [Path(path).name for path in locations_file.read_text(encoding = "utf-8").split()]
        self.assertIn("dslx_stdlib", basenames)
        self.assertTrue(any(name.startswith("libxls") for name in basenames))
        self.assertFalse(any(name == "xlsynth-driver" for name in basenames))

    def test_xlsynth_sys_legacy_exports_are_stdlib_plus_dso(self):
        runfiles_lookup = runfiles.Create()
        workspace = os.environ["TEST_WORKSPACE"]

        locations_file = Path(
            runfiles_lookup.Rlocation("{}/xlsynth_sys_legacy_input_locations.txt".format(workspace)),
        )
        self.assertTrue(locations_file.is_file())

        basenames = [Path(path).name for path in locations_file.read_text(encoding = "utf-8").split()]
        self.assertIn("dslx_stdlib", basenames)
        self.assertTrue(any(name.startswith("libxls") for name in basenames))


if __name__ == "__main__":
    unittest.main()
