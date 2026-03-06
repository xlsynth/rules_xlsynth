# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_build_driver_install_environment_uses_platform_scoped_cache_dirs(self):
        libxls_path = "/tmp/xls-bundle/libxls.dylib" if sys.platform == "darwin" else "/tmp/xls-bundle/libxls.so"
        env = materialize_xls_bundle.build_driver_install_environment(
            Path("/tmp/xls-bundle-repo"),
            libxls_path = libxls_path,
            dslx_stdlib_path = "/tmp/xls-bundle",
            host_platform = "arm64",
        )
        self.assertEqual(env["RUSTUP_HOME"], "/tmp/xls-bundle-repo/_rustup_home/arm64")
        self.assertEqual(env["CARGO_TARGET_DIR"], "/tmp/xls-bundle-repo/_cargo_target/arm64")

    def test_driver_install_root_is_version_and_platform_scoped(self):
        self.assertEqual(
            materialize_xls_bundle.driver_install_root(
                Path("/tmp/xls-bundle-repo"),
                "0.33.0",
                "arm64",
            ),
            Path("/tmp/xls-bundle-repo/_cargo_driver/arm64/0.33.0"),
        )

    def test_download_versioned_artifacts_reuses_valid_cache(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            download_root = repo_root / "_downloaded_xls" / "arm64" / "0.38.0"
            (download_root / "xls" / "dslx" / "stdlib").mkdir(parents = True)
            (download_root / "xls" / "dslx" / "stdlib" / "std.x").write_text("// stdlib\n", encoding = "utf-8")
            for binary in materialize_xls_bundle.TOOL_BINARIES:
                (download_root / binary).write_text("", encoding = "utf-8")
            (download_root / "libxls-v0.38.0-arm64.dylib").write_text("", encoding = "utf-8")

            with mock.patch.object(materialize_xls_bundle, "detect_host_platform", return_value = "arm64"):
                with mock.patch.object(materialize_xls_bundle.subprocess, "run") as mock_run:
                    resolved = materialize_xls_bundle.download_versioned_artifacts(repo_root, "0.38.0")

            self.assertEqual(resolved["tools_root"], download_root)
            self.assertEqual(resolved["dslx_stdlib_root"], download_root / "xls" / "dslx" / "stdlib")
            self.assertEqual(
                resolved["libxls"],
                download_root / "libxls-v0.38.0-arm64.dylib",
            )
            mock_run.assert_not_called()

    def test_install_driver_reuses_valid_cached_binary(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            driver_path = repo_root / "_cargo_driver" / "arm64" / "0.33.0" / "bin" / "xlsynth-driver"
            driver_path.parent.mkdir(parents = True)
            driver_path.write_text("", encoding = "utf-8")

            with mock.patch.object(materialize_xls_bundle, "detect_host_platform", return_value = "arm64"):
                with mock.patch.object(materialize_xls_bundle.shutil, "which") as mock_which:
                    with mock.patch.object(
                        materialize_xls_bundle.subprocess,
                        "run",
                        return_value = mock.Mock(
                            returncode = 0,
                            stdout = "xlsynth-driver 0.33.0\n",
                            stderr = "",
                        ),
                    ) as mock_run:
                        resolved = materialize_xls_bundle.install_driver(
                            repo_root = repo_root,
                            driver_version = "0.33.0",
                            libxls_path = "/tmp/xls-bundle/libxls.dylib" if sys.platform == "darwin" else "/tmp/xls-bundle/libxls.so",
                            dslx_stdlib_path = "/tmp/xls-bundle",
                        )

            self.assertEqual(resolved, driver_path)
            mock_which.assert_not_called()
            mock_run.assert_called_once_with(
                [str(driver_path), "--version"],
                check = False,
                capture_output = True,
                text = True,
                env = mock.ANY,
            )

    def test_parse_readelf_soname_finds_soname(self):
        self.assertEqual(
            materialize_xls_bundle.parse_readelf_soname(
                """
Tag        Type                         Name/Value
0x000000000000000e (SONAME)             Library soname: [libxls-v0.38.0.so]
"""
            ),
            "libxls-v0.38.0.so",
        )

    def test_read_linux_soname_reads_elf_metadata(self):
        with mock.patch.object(
            materialize_xls_bundle.subprocess,
            "run",
            return_value = mock.Mock(
                returncode = 0,
                stdout = "0x000000000000000e (SONAME)             Library soname: [libxls-v0.38.0.so]\n",
                stderr = "",
            ),
        ):
            self.assertEqual(
                materialize_xls_bundle.read_linux_soname(Path("/tmp/xls-bundle/libxls.so")),
                "libxls-v0.38.0.so",
            )

    def test_normalize_linux_soname_sets_expected_name(self):
        with mock.patch.object(
            materialize_xls_bundle,
            "read_linux_soname",
            return_value = "libxls-v0.38.0.so",
        ):
            with mock.patch.object(materialize_xls_bundle.shutil, "which", return_value = "/usr/bin/patchelf"):
                with mock.patch.object(materialize_xls_bundle.subprocess, "run") as mock_run:
                    materialize_xls_bundle.normalize_linux_soname(Path("/tmp/xls-bundle/libxls.so"))
        mock_run.assert_called_once_with(
            [
                "/usr/bin/patchelf",
                "--set-soname",
                "libxls.so",
                "/tmp/xls-bundle/libxls.so",
            ],
            check = True,
        )

    def test_normalize_linux_soname_is_noop_when_matching(self):
        with mock.patch.object(
            materialize_xls_bundle,
            "read_linux_soname",
            return_value = "libxls.so",
        ):
            with mock.patch.object(materialize_xls_bundle.shutil, "which") as mock_which:
                with mock.patch.object(materialize_xls_bundle.subprocess, "run") as mock_run:
                    materialize_xls_bundle.normalize_linux_soname(Path("/tmp/xls-bundle/libxls.so"))
        mock_which.assert_not_called()
        mock_run.assert_not_called()

    def test_normalize_linux_soname_raises_when_patchelf_missing(self):
        with mock.patch.object(
            materialize_xls_bundle,
            "read_linux_soname",
            return_value = "libxls-v0.38.0.so",
        ):
            with mock.patch.object(materialize_xls_bundle.shutil, "which", return_value = None):
                with self.assertRaises(RuntimeError):
                    materialize_xls_bundle.normalize_linux_soname(
                        Path("/tmp/xls-bundle/libxls.so"),
                    )


if __name__ == "__main__":
    unittest.main()
