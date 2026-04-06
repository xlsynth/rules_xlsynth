# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import materialize_xls_bundle


class ArtifactResolutionTest(unittest.TestCase):
    def test_auto_prefers_exact_installed_layout(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "auto",
            xls_version = "0.38.0",
            driver_version = "0.33.0",
            installed_tools_root_prefix = "/tools/xlsynth",
            installed_driver_root_prefix = "/tools/xlsynth-driver",
            exists_fn = lambda path: True,
        )
        self.assertEqual(plan["mode"], "installed")
        self.assertEqual(
            plan["dslx_stdlib_root"],
            Path("/tools/xlsynth/v0.38.0/xls/dslx/stdlib"),
        )
        self.assertEqual(
            materialize_xls_bundle.derive_runtime_library_path(plan["libxls"]),
            "/tools/xlsynth/v0.38.0",
        )

    def test_auto_falls_back_to_download(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "auto",
            xls_version = "0.38.0",
            driver_version = "0.33.0",
            installed_tools_root_prefix = "/tools/xlsynth",
            installed_driver_root_prefix = "/tools/xlsynth-driver",
            exists_fn = lambda path: False,
        )
        self.assertEqual(plan["mode"], "download")
        self.assertEqual(plan["xls_version"], "0.38.0")
        self.assertEqual(plan["driver_version"], "0.33.0")

    def test_auto_requires_installed_prefixes(self):
        with self.assertRaises(ValueError):
            materialize_xls_bundle.resolve_artifact_plan(
                artifact_source = "auto",
                xls_version = "0.38.0",
                driver_version = "0.33.0",
                exists_fn = lambda path: False,
            )

    def test_installed_only_requires_installed_paths(self):
        with self.assertRaises(ValueError):
            materialize_xls_bundle.resolve_artifact_plan(
                artifact_source = "installed_only",
                xls_version = "0.38.0",
                driver_version = "0.33.0",
                installed_tools_root_prefix = "/tools/xlsynth",
                installed_driver_root_prefix = "/tools/xlsynth-driver",
                exists_fn = lambda path: False,
            )

    def test_download_only_skips_installed_probe(self):
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

    def test_download_only_rejects_installed_prefixes(self):
        with self.assertRaises(ValueError):
            materialize_xls_bundle.resolve_artifact_plan(
                artifact_source = "download_only",
                xls_version = "0.38.0",
                driver_version = "0.33.0",
                installed_tools_root_prefix = "/tools/xlsynth",
                installed_driver_root_prefix = "/tools/xlsynth-driver",
            )

    def test_detect_host_platform_rejects_intel_macos(self):
        with mock.patch.object(materialize_xls_bundle.sys, "platform", "darwin"):
            with mock.patch.object(materialize_xls_bundle.os, "uname", return_value = mock.Mock(machine = "x86_64")):
                with self.assertRaisesRegex(RuntimeError, "Intel macOS"):
                    materialize_xls_bundle.detect_host_platform()

    def test_installed_paths_use_live_version_pattern(self):
        plan = materialize_xls_bundle.derive_installed_paths(
            xls_version = "0.38.0",
            driver_version = "0.33.0",
            installed_tools_root_prefix = "/eda-tools/xlsynth",
            installed_driver_root_prefix = "/eda-tools/xlsynth-driver",
        )
        self.assertEqual(plan["tools_root"], Path("/eda-tools/xlsynth/v0.38.0"))
        self.assertEqual(plan["driver"], Path("/eda-tools/xlsynth-driver/0.33.0/bin/xlsynth-driver"))
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

    def test_detect_driver_capabilities_reads_help_flags(self):
        with mock.patch.object(
            materialize_xls_bundle.subprocess,
            "run",
            return_value = mock.Mock(
                returncode = 0,
                stdout = "Usage: xlsynth-driver dslx2sv-types --sv_struct_field_ordering <POLICY>\n",
                stderr = "--sv_enum_case_naming_policy <POLICY>\n",
            ),
        ):
            self.assertEqual(
                materialize_xls_bundle.detect_driver_capabilities(
                    Path("/tmp/xls-bundle/xlsynth-driver"),
                    Path("/tmp/xls-bundle/libxls.so"),
                    Path("/tmp/xls-bundle"),
                ),
                {
                    "driver_supports_sv_enum_case_naming_policy": True,
                    "driver_supports_sv_struct_field_ordering": True,
                },
            )

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
            self.assertEqual(resolved["runtime_files"], [])
            mock_run.assert_not_called()

    def test_load_runtime_manifest_returns_runtime_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "libc++.so.1").write_text("", encoding = "utf-8")
            (root / "libc++abi.so.1").write_text("", encoding = "utf-8")
            (root / "libxls-runtime-ubuntu2004-manifest.json").write_text(
                '{"runtime_files": ["libc++.so.1", "libc++abi.so.1"]}\n',
                encoding = "utf-8",
            )

            self.assertEqual(
                materialize_xls_bundle.load_runtime_manifest(root),
                [
                    root / "libc++.so.1",
                    root / "libc++abi.so.1",
                ],
            )

    def test_load_runtime_manifest_returns_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            self.assertEqual(materialize_xls_bundle.load_runtime_manifest(Path(tempdir)), [])

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
                stdout = materialize_xls_bundle.subprocess.PIPE,
                stderr = materialize_xls_bundle.subprocess.PIPE,
                universal_newlines = True,
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
        ) as mock_run:
            self.assertEqual(
                materialize_xls_bundle.read_linux_soname(Path("/tmp/xls-bundle/libxls.so")),
                "libxls-v0.38.0.so",
            )
        mock_run.assert_called_once_with(
            ["readelf", "-d", "/tmp/xls-bundle/libxls.so"],
            check = False,
            stdout = materialize_xls_bundle.subprocess.PIPE,
            stderr = materialize_xls_bundle.subprocess.PIPE,
            universal_newlines = True,
            env = None,
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
                    self.assertEqual(
                        materialize_xls_bundle.normalize_linux_soname(Path("/tmp/xls-bundle/libxls.so")),
                        [],
                    )
        mock_which.assert_not_called()
        mock_run.assert_not_called()

    def test_normalize_linux_soname_stages_runtime_alias_when_patchelf_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            libxls_path = Path(tempdir) / "libxls.so"
            libxls_path.write_text("xls\n", encoding = "utf-8")

            with mock.patch.object(
                materialize_xls_bundle,
                "read_linux_soname",
                return_value = "libxls-v0.38.0.so",
            ):
                with mock.patch.object(materialize_xls_bundle.shutil, "which", return_value = None):
                    with mock.patch.object(materialize_xls_bundle.subprocess, "run") as mock_run:
                        self.assertEqual(
                            materialize_xls_bundle.normalize_linux_soname(libxls_path),
                            ["libxls-v0.38.0.so"],
                        )

            alias_path = Path(tempdir) / "libxls-v0.38.0.so"
            self.assertTrue(alias_path.exists())
            if alias_path.is_symlink():
                self.assertEqual(os.readlink(alias_path), "libxls.so")
            else:
                self.assertEqual(alias_path.read_text(encoding = "utf-8"), "xls\n")
            mock_run.assert_not_called()

    def test_stage_runtime_payload_records_runtime_metadata(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            input_root = repo_root / "_inputs"
            tools_root = input_root / "tools"
            stdlib_root = tools_root / "xls" / "dslx" / "stdlib"
            stdlib_root.mkdir(parents = True)
            (stdlib_root / "std.x").write_text("// stdlib\n", encoding = "utf-8")
            for binary in materialize_xls_bundle.TOOL_BINARIES:
                (tools_root / binary).write_text("", encoding = "utf-8")

            libxls_path = input_root / "libxls-v0.38.0.so"
            libxls_path.write_text("xls\n", encoding = "utf-8")
            runtime_companion = input_root / "libc++.so.1"
            runtime_companion.write_text("runtime\n", encoding = "utf-8")

            with mock.patch.object(
                materialize_xls_bundle,
                "normalize_runtime_library_identity",
                return_value = ["libxls-v0.38.0.so"],
            ):
                materialize_xls_bundle.stage_runtime_payload(
                    repo_root,
                    {
                        "tools_root": tools_root,
                        "dslx_stdlib_root": stdlib_root,
                        "libxls": libxls_path,
                        "runtime_files": [runtime_companion],
                    },
                )

            metadata = dict(
                line.split("=", 1)
                for line in (repo_root / "runtime_metadata.txt").read_text(encoding = "utf-8").splitlines()
                if line
            )
            self.assertEqual(metadata["libxls_name"], "libxls.so")
            self.assertEqual(metadata["libxls_runtime_aliases"], "libxls-v0.38.0.so")
            self.assertEqual(metadata["libxls_runtime_files"], "libc++.so.1")
            self.assertTrue((repo_root / "libc++.so.1").is_file())

    def test_materialize_toolchain_surface_records_driver_capabilities(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            input_root = repo_root / "_inputs"
            stdlib_root = input_root / "xls" / "dslx" / "stdlib"
            stdlib_root.mkdir(parents = True)
            (stdlib_root / "std.x").write_text("// stdlib\n", encoding = "utf-8")

            driver_path = input_root / "xlsynth-driver"
            driver_path.write_text("", encoding = "utf-8")
            libxls_path = input_root / "libxls.so"
            libxls_path.write_text("xls\n", encoding = "utf-8")
            runtime_companion = input_root / "libc++.so.1"
            runtime_companion.write_text("runtime\n", encoding = "utf-8")

            with mock.patch.object(
                materialize_xls_bundle,
                "resolve_materialization_inputs",
                return_value = {
                    "mode": "installed",
                    "driver": driver_path,
                    "dslx_stdlib_root": stdlib_root,
                    "libxls": libxls_path,
                    "runtime_files": [runtime_companion],
                },
            ):
                with mock.patch.object(
                    materialize_xls_bundle,
                    "detect_driver_capabilities",
                    return_value = {
                        "driver_supports_sv_enum_case_naming_policy": True,
                        "driver_supports_sv_struct_field_ordering": False,
                    },
                ):
                    with mock.patch.object(
                        materialize_xls_bundle,
                        "normalize_runtime_library_identity",
                        return_value = [],
                    ):
                        materialize_xls_bundle.materialize_toolchain_surface(
                            repo_root,
                            {"mode": "installed"},
                        )

            metadata = dict(
                line.split("=", 1)
                for line in (repo_root / "toolchain_metadata.txt").read_text(encoding = "utf-8").splitlines()
                if line
            )
            self.assertEqual(metadata["driver_supports_sv_enum_case_naming_policy"], "true")
            self.assertEqual(metadata["driver_supports_sv_struct_field_ordering"], "false")
            self.assertTrue((repo_root / "xlsynth-driver").exists())


if __name__ == "__main__":
    unittest.main()
