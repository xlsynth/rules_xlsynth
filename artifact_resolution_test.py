# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import sys
import unittest

import materialize_xls_bundle


class ArtifactResolutionTest(unittest.TestCase):
    def test_auto_prefers_exact_eda_tools_layout(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "auto",
            xls_version = "0.38.0",
            driver_version = "0.33.0",
            exists_fn = lambda path: True,
        )
        self.assertEqual(plan["mode"], "eda_tools")
        self.assertTrue(str(plan["dslx_stdlib_root"]).endswith("/eda-tools/xlsynth/v0.38.0/xls/dslx/stdlib"))
        self.assertEqual(
            materialize_xls_bundle.derive_runtime_library_path(plan["libxls"]),
            "/eda-tools/xlsynth/v0.38.0",
        )

    def test_auto_falls_back_to_download(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "auto",
            xls_version = "0.38.0",
            driver_version = "0.33.0",
            exists_fn = lambda path: False,
        )
        self.assertEqual(plan["mode"], "download")
        self.assertEqual(plan["xls_version"], "0.38.0")
        self.assertEqual(plan["driver_version"], "0.33.0")

    def test_eda_tools_only_requires_installed_paths(self):
        with self.assertRaises(ValueError):
            materialize_xls_bundle.resolve_artifact_plan(
                artifact_source = "eda_tools_only",
                xls_version = "0.38.0",
                driver_version = "0.33.0",
                exists_fn = lambda path: False,
            )

    def test_download_only_skips_eda_tools_probe(self):
        observed_paths = []

        def exists_fn(path):
            observed_paths.append(path)
            return True

        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "download_only",
            xls_version = "0.38.0",
            driver_version = "0.33.0",
            exists_fn = exists_fn,
        )
        self.assertEqual(plan["mode"], "download")
        self.assertEqual(observed_paths, [])

    def test_local_paths_bypass_versioned_selection(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "local_paths",
            xls_version = "",
            driver_version = "",
            local_tools_path = "/tmp/xls-local-dev/tools",
            local_dslx_stdlib_path = "/tmp/xls-local-dev/stdlib",
            local_driver_path = "/tmp/xls-local-dev/xlsynth-driver",
            local_libxls_path = "/tmp/xls-local-dev/libxls.so",
        )
        self.assertEqual(plan["mode"], "local_paths")
        self.assertEqual(
            materialize_xls_bundle.derive_runtime_library_path(plan["libxls"]),
            "/tmp/xls-local-dev",
        )

    def test_eda_tools_paths_use_host_specific_libxls_name(self):
        plan = materialize_xls_bundle.derive_eda_tools_paths("0.38.0", "0.33.0")
        expected_name = "libxls.dylib" if sys.platform == "darwin" else "libxls.so"
        self.assertEqual(plan["libxls"].name, expected_name)

    def test_build_driver_environment_sets_runtime_library_search_path(self):
        libxls_path = "/tmp/xls-bundle/libxls.dylib" if sys.platform == "darwin" else "/tmp/xls-bundle/libxls.so"
        runtime_var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        env = materialize_xls_bundle.build_driver_environment(
            libxls_path = libxls_path,
            dslx_stdlib_path = "/tmp/xls-bundle",
            environ = {
                runtime_var: "/existing/runtime/path",
            },
            sys_platform = sys.platform,
        )
        self.assertEqual(
            env[runtime_var],
            "/tmp/xls-bundle{}{}".format(os.pathsep, "/existing/runtime/path"),
        )
        self.assertEqual(env["XLS_DSO_PATH"], libxls_path)
        self.assertEqual(env["DSLX_STDLIB_PATH"], "/tmp/xls-bundle")

    def test_build_driver_install_command_uses_rustup_nightly(self):
        command = materialize_xls_bundle.build_driver_install_command(
            "/usr/bin/rustup",
            "/tmp/xls-driver-root",
            "0.33.0",
        )
        self.assertEqual(
            command,
            [
                "/usr/bin/rustup",
                "run",
                "nightly",
                "cargo",
                "install",
                "--locked",
                "--root",
                "/tmp/xls-driver-root",
                "--version",
                "0.33.0",
                "xlsynth-driver",
            ],
        )

    def test_build_rustup_toolchain_install_command_uses_minimal_profile(self):
        command = materialize_xls_bundle.build_rustup_toolchain_install_command("/usr/bin/rustup")
        self.assertEqual(
            command,
            [
                "/usr/bin/rustup",
                "toolchain",
                "install",
                "nightly",
                "--profile",
                "minimal",
            ],
        )

    def test_build_driver_install_environment_uses_repo_local_cargo_and_rustup_homes(self):
        libxls_path = "/tmp/xls-bundle/libxls.dylib" if sys.platform == "darwin" else "/tmp/xls-bundle/libxls.so"
        env = materialize_xls_bundle.build_driver_install_environment(
            Path("/tmp/xls-bundle-repo"),
            libxls_path = libxls_path,
            dslx_stdlib_path = "/tmp/xls-bundle",
        )
        self.assertEqual(env["CARGO_HOME"], "/tmp/xls-bundle-repo/_cargo_home")
        self.assertEqual(env["RUSTUP_HOME"], "/tmp/xls-bundle-repo/_rustup_home")
        self.assertEqual(env["CARGO_TARGET_DIR"], "/tmp/xls-bundle-repo/_cargo_target")


if __name__ == "__main__":
    unittest.main()
