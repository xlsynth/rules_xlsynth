# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path
import sys
import tarfile
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

    def test_runtime_surface_does_not_require_or_select_driver(self):
        observed_paths = []

        def exists_fn(path):
            observed_paths.append(path)
            return path != "/tools/xlsynth/v0.38.0/xlsynth-driver-sentinel"

        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "auto",
            xls_version = "0.38.0",
            driver_version = "",
            surface = "runtime",
            installed_tools_root_prefix = "/tools/xlsynth",
            installed_driver_root_prefix = "",
            exists_fn = exists_fn,
        )
        self.assertEqual(plan["mode"], "installed")
        self.assertNotIn("driver", plan)
        self.assertNotIn("driver_version", plan)
        self.assertEqual(
            observed_paths,
            [
                "/tools/xlsynth/v0.38.0",
                "/tools/xlsynth/v0.38.0/xls/dslx/stdlib",
                "/tools/xlsynth/v0.38.0/libxls.dylib" if sys.platform == "darwin" else "/tools/xlsynth/v0.38.0/libxls.so",
                "/tools/xlsynth/v0.38.0/libxls_aot_runtime.a",
                "/tools/xlsynth/v0.38.0/libxls_aot_runtime_link.toml",
                "/tools/xlsynth/v0.38.0/xls-aot-runtime-source.tar.gz",
            ],
        )

    def test_runtime_local_paths_does_not_require_local_driver_path(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "local_paths",
            xls_version = "",
            driver_version = "",
            surface = "runtime",
            local_tools_path = "/tmp/xls-local-dev/tools",
            local_dslx_stdlib_path = "/tmp/xls-local-dev/stdlib",
            local_libxls_path = "/tmp/xls-local-dev/libxls.so",
        )
        self.assertEqual(plan["mode"], "local_paths")
        self.assertNotIn("driver", plan)

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

    def test_installed_paths_require_static_aot_runtime_pair(self):
        with self.assertRaisesRegex(ValueError, "together"):
            materialize_xls_bundle.resolve_artifact_plan(
                artifact_source = "installed_only",
                xls_version = "0.38.0",
                driver_version = "0.33.0",
                installed_tools_root_prefix = "/tools/xlsynth",
                installed_driver_root_prefix = "/tools/xlsynth-driver",
                exists_fn = lambda path: not path.endswith("libxls_aot_runtime_link.toml"),
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

    def test_download_only_can_use_local_aot_runtime_source(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "download_only",
            xls_version = "0.38.0",
            driver_version = "0.33.0",
            local_xls_aot_runtime_source_path = "/tmp/review/xls-aot-runtime-source.tar.gz",
        )
        self.assertEqual(plan["mode"], "download")
        self.assertEqual(
            plan["xls_aot_runtime_source"],
            Path("/tmp/review/xls-aot-runtime-source.tar.gz"),
        )

    def test_local_paths_bypass_versioned_selection(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "local_paths",
            xls_version = "",
            driver_version = "",
            local_tools_path = "/tmp/xls-local-dev/tools",
            local_dslx_stdlib_path = "/tmp/xls-local-dev/stdlib",
            local_driver_path = "/tmp/xls-local-dev/xlsynth-driver",
            local_libxls_path = "/tmp/xls-local-dev/libxls.so",
            local_xls_aot_runtime_path = "/tmp/xls-local-dev/libxls_aot_runtime.a",
            local_xls_aot_runtime_link_config_path = "/tmp/xls-local-dev/libxls_aot_runtime_link.toml",
        )
        self.assertEqual(plan["mode"], "local_paths")
        self.assertEqual(
            materialize_xls_bundle.derive_runtime_library_path(plan["libxls"]),
            "/tmp/xls-local-dev",
        )
        self.assertEqual(
            plan["xls_aot_runtime"],
            Path("/tmp/xls-local-dev/libxls_aot_runtime.a"),
        )
        self.assertEqual(
            plan["xls_aot_runtime_link_config"],
            Path("/tmp/xls-local-dev/libxls_aot_runtime_link.toml"),
        )

    def test_local_paths_allow_bundle_without_static_aot_runtime(self):
        plan = materialize_xls_bundle.resolve_artifact_plan(
            artifact_source = "local_paths",
            xls_version = "",
            driver_version = "",
            local_tools_path = "/tmp/xls-local-dev/tools",
            local_dslx_stdlib_path = "/tmp/xls-local-dev/stdlib",
            local_driver_path = "/tmp/xls-local-dev/xlsynth-driver",
            local_libxls_path = "/tmp/xls-local-dev/libxls.so",
        )
        self.assertIsNone(plan["xls_aot_runtime"])
        self.assertIsNone(plan["xls_aot_runtime_link_config"])

    def test_local_paths_require_static_aot_runtime_pair(self):
        with self.assertRaisesRegex(ValueError, "together"):
            materialize_xls_bundle.resolve_artifact_plan(
                artifact_source = "local_paths",
                xls_version = "",
                driver_version = "",
                local_tools_path = "/tmp/xls-local-dev/tools",
                local_dslx_stdlib_path = "/tmp/xls-local-dev/stdlib",
                local_driver_path = "/tmp/xls-local-dev/xlsynth-driver",
                local_libxls_path = "/tmp/xls-local-dev/libxls.so",
                local_xls_aot_runtime_path = "/tmp/xls-local-dev/libxls_aot_runtime.a",
            )

    def test_resolve_driver_plan_prefers_installed_driver(self):
        plan = materialize_xls_bundle.resolve_driver_plan(
            artifact_source = "auto",
            driver_version = "0.33.0",
            installed_driver_root_prefix = "/tools/xlsynth-driver",
            exists_fn = lambda path: True,
        )
        self.assertEqual(plan["mode"], "auto_installed")
        self.assertEqual(plan["driver"], Path("/tools/xlsynth-driver/0.33.0/bin/xlsynth-driver"))

    def test_resolve_driver_plan_auto_falls_back_to_download(self):
        plan = materialize_xls_bundle.resolve_driver_plan(
            artifact_source = "auto",
            driver_version = "0.33.0",
            installed_driver_root_prefix = "/tools/xlsynth-driver",
            exists_fn = lambda path: False,
        )
        self.assertEqual(plan, {"mode": "download", "driver_version": "0.33.0"})

    def test_resolve_driver_plan_uses_declared_installed_driver_input(self):
        plan = materialize_xls_bundle.resolve_driver_plan(
            artifact_source = "auto",
            driver_version = "0.33.0",
            installed_driver_root_prefix = "/unavailable/xlsynth-driver",
            driver_input = "external/toolchain/host_xlsynth-driver",
            exists_fn = lambda path: False,
        )
        self.assertEqual(plan["mode"], "auto_driver_input")
        self.assertEqual(plan["driver"], Path("external/toolchain/host_xlsynth-driver"))
        self.assertEqual(plan["driver_version"], "0.33.0")
        self.assertEqual(plan["installed_driver_root_prefix"], "/unavailable/xlsynth-driver")

    def test_resolve_driver_plan_rejects_declared_local_driver_input_without_plan_path(self):
        with self.assertRaisesRegex(ValueError, "local_paths driver materialization requires local_driver_path"):
            materialize_xls_bundle.resolve_driver_plan(
                artifact_source = "local_paths",
                driver_version = "",
                local_driver_path = "",
                driver_input = "external/toolchain/host_xlsynth-driver",
            )

    def test_resolve_driver_plan_rejects_declared_local_driver_input_mismatch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            configured_driver = root / "configured" / "xlsynth-driver"
            configured_driver.parent.mkdir()
            configured_driver.write_text("#!/bin/sh\nexit 0\n", encoding = "utf-8")
            configured_driver.chmod(0o755)
            declared_driver = root / "declared" / "host_xlsynth-driver"
            declared_driver.parent.mkdir()
            declared_driver.write_text("#!/bin/sh\nexit 127\n", encoding = "utf-8")
            declared_driver.chmod(0o755)

            with self.assertRaisesRegex(ValueError, "local_paths declared driver input must match local_driver_path"):
                materialize_xls_bundle.resolve_driver_plan(
                    artifact_source = "local_paths",
                    driver_version = "",
                    local_driver_path = str(configured_driver),
                    driver_input = str(declared_driver),
                )

    def test_resolve_driver_plan_uses_declared_local_driver_input_matching_plan_path(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            configured_driver = root / "configured" / "xlsynth-driver"
            configured_driver.parent.mkdir()
            configured_driver.write_text("#!/bin/sh\nexit 0\n", encoding = "utf-8")
            configured_driver.chmod(0o755)
            declared_driver = root / "declared" / "host_xlsynth-driver"
            declared_driver.parent.mkdir()
            declared_driver.symlink_to(configured_driver)

            plan = materialize_xls_bundle.resolve_driver_plan(
                artifact_source = "local_paths",
                driver_version = "",
                local_driver_path = str(configured_driver),
                driver_input = str(declared_driver),
            )
            self.assertEqual(
                plan,
                {
                    "mode": "local_paths",
                    "driver": declared_driver,
                },
            )

    def test_auto_driver_input_materialization_falls_back_when_declared_input_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            declared_driver = root / "declared" / "host_xlsynth-driver"
            declared_driver.parent.mkdir()
            declared_driver.write_text("", encoding = "utf-8")
            declared_driver.chmod(0o755)

            fallback_driver = root / "installed" / "0.33.0" / "bin" / "xlsynth-driver"
            fallback_driver.parent.mkdir(parents = True)
            fallback_driver.write_text(
                """#!/bin/sh
if [ "${1:-}" = "--version" ]; then
  printf 'xlsynth-driver 0.33.0 fallback\\n'
  exit 0
fi
printf 'fallback body\\n'
""",
                encoding = "utf-8",
            )
            fallback_driver.chmod(0o755)

            output_driver = root / "out" / "xlsynth-driver"
            with mock.patch.object(
                materialize_xls_bundle,
                "install_driver",
                return_value = fallback_driver,
            ) as mock_install:
                materialize_xls_bundle.materialize_driver_binary(
                    repo_root = root / "repo",
                    plan = {
                        "mode": "auto_driver_input",
                        "driver": declared_driver,
                        "driver_version": "0.33.0",
                        "installed_driver_root_prefix": str(root / "installed"),
                    },
                    driver_output = output_driver,
                    libxls_path = root / "runtime" / "libxls.so",
                    dslx_stdlib_path = root / "stdlib",
                )
            mock_install.assert_called_once_with(
                root / "repo",
                "0.33.0",
                root / "runtime" / "libxls.so",
                root / "stdlib",
                rustup_path = "",
                driver_git_revision = "",
            )
            self.assertIn("fallback body", output_driver.read_text(encoding = "utf-8"))

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
        self.assertEqual(plan["xls_aot_runtime"].name, "libxls_aot_runtime.a")
        self.assertEqual(
            plan["xls_aot_runtime_link_config"].name,
            "libxls_aot_runtime_link.toml",
        )
        self.assertEqual(
            plan["xls_aot_runtime_source"].name,
            "xls-aot-runtime-source.tar.gz",
        )

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

    def test_build_driver_git_install_command_uses_exact_revision(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        command = materialize_xls_bundle.build_driver_git_install_command(
            "/usr/bin/rustup",
            "/tmp/xls-driver-root",
            revision,
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
                "--git",
                "https://github.com/xlsynth/xlsynth-crate.git",
                "--rev",
                revision,
                "xlsynth-driver",
            ],
        )

    def test_resolve_driver_plan_uses_git_revision_as_installed_layout_key(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        plan = materialize_xls_bundle.resolve_driver_plan(
            artifact_source = "auto",
            driver_version = "",
            driver_git_revision = revision,
            installed_driver_root_prefix = "/tools/xlsynth-driver",
            exists_fn = lambda path: True,
        )
        self.assertEqual(plan["mode"], "auto_installed")
        self.assertEqual(
            plan["driver"],
            Path("/tools/xlsynth-driver") / revision / "bin" / "xlsynth-driver",
        )
        self.assertEqual(plan["driver_git_revision"], revision)

    def test_resolve_archive_identity_keeps_crate_and_xls_versions_independent(self):
        crate_revision = "c6a302d21568ce424143d49c1b31b3e14ed70035"
        xls_revision = "8c5c112b4563401d33b4da1dcd4d7f69db54e0e5"
        observed_urls = []

        def list_remote_tags(repo_url):
            if repo_url == "https://github.com/xlsynth/xlsynth-crate.git":
                return {"v0.50.0": crate_revision}
            return {"v0.50.1": xls_revision}

        def read_text(url):
            observed_urls.append(url)
            return 'const RELEASE_LIB_VERSION_TAG: &str = "v0.50.1";\n'

        identity = materialize_xls_bundle.resolve_archive_identity(
            xls_version = "0.50.1",
            xls_git_revision = "",
            driver_version = "0.50.0",
            driver_git_revision = "",
            list_remote_tags_fn = list_remote_tags,
            read_text_fn = read_text,
        )

        self.assertEqual(
            identity,
            {
                "schema_version": 1,
                "xlsynth_crate_pin": {
                    "kind": "release_tag",
                    "value": "v0.50.0",
                },
                "xls_pin": {
                    "kind": "release_tag",
                    "value": "v0.50.1",
                },
                "resolved_xlsynth_crate_revision": crate_revision,
                "crate_implied_xls_release_tag": "v0.50.1",
                "resolved_xls_release_tag": "v0.50.1",
                "resolved_xls_revision": xls_revision,
            },
        )
        self.assertEqual(
            observed_urls,
            [
                "https://raw.githubusercontent.com/xlsynth/xlsynth-crate/{}/xlsynth-sys/build.rs".format(
                    crate_revision,
                ),
            ],
        )

    def test_resolve_archive_identity_accepts_fetchable_crate_git_revision(self):
        crate_revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        xls_revision = "8c5c112b4563401d33b4da1dcd4d7f69db54e0e5"
        observed_urls = []

        def read_text(url):
            observed_urls.append(url)
            return 'const RELEASE_LIB_VERSION_TAG: &str = "v0.50.1";\n'

        identity = materialize_xls_bundle.resolve_archive_identity(
            xls_version = "v0.50.1",
            xls_git_revision = "",
            driver_version = "",
            driver_git_revision = crate_revision,
            list_remote_tags_fn = lambda _repo_url: {"v0.50.1": xls_revision},
            read_text_fn = read_text,
        )

        self.assertEqual(identity["xlsynth_crate_pin"]["kind"], "git_revision")
        self.assertEqual(identity["resolved_xlsynth_crate_revision"], crate_revision)
        self.assertEqual(
            observed_urls,
            [
                "https://raw.githubusercontent.com/xlsynth/xlsynth-crate/{}/xlsynth-sys/build.rs".format(
                    crate_revision,
                ),
            ],
        )

    def test_resolve_archive_identity_rejects_unresolvable_crate_git_revision(self):
        with self.assertRaisesRegex(ValueError, "could not be resolved"):
            materialize_xls_bundle.resolve_archive_identity(
                xls_version = "v0.50.1",
                xls_git_revision = "",
                driver_version = "",
                driver_git_revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be",
                list_remote_tags_fn = lambda _repo_url: {
                    "v0.50.1": "8c5c112b4563401d33b4da1dcd4d7f69db54e0e5",
                },
                read_text_fn = lambda _url: (_ for _ in ()).throw(OSError("not found")),
            )

    def test_resolve_archive_identity_maps_xls_git_revision_to_published_release(self):
        crate_revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        xls_revision = "8c5c112b4563401d33b4da1dcd4d7f69db54e0e5"
        identity = materialize_xls_bundle.resolve_archive_identity(
            xls_version = "",
            xls_git_revision = xls_revision,
            driver_version = "",
            driver_git_revision = crate_revision,
            list_remote_tags_fn = lambda _repo_url: {"v0.50.1": xls_revision},
            read_text_fn = lambda _url: 'const RELEASE_LIB_VERSION_TAG: &str = "v0.50.1";\n',
        )

        self.assertEqual(
            identity["xls_pin"],
            {
                "kind": "git_revision",
                "value": xls_revision,
            },
        )
        self.assertEqual(identity["resolved_xls_release_tag"], "v0.50.1")

    def test_resolve_archive_identity_rejects_unpublished_xls_git_revision(self):
        with self.assertRaisesRegex(ValueError, "does not map to a published XLS release tag"):
            materialize_xls_bundle.resolve_archive_identity(
                xls_version = "",
                xls_git_revision = "8c5c112b4563401d33b4da1dcd4d7f69db54e0e5",
                driver_version = "",
                driver_git_revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be",
                list_remote_tags_fn = lambda _repo_url: {},
                read_text_fn = lambda _url: 'const RELEASE_LIB_VERSION_TAG: &str = "v0.50.1";\n',
            )

    def test_resolve_archive_identity_requires_explicit_mismatch_override(self):
        kwargs = {
            "xls_version": "v0.50.1",
            "xls_git_revision": "",
            "driver_version": "",
            "driver_git_revision": "0910ee19072a39a960b8df85b4f1e25199a4b4be",
            "list_remote_tags_fn": lambda _repo_url: {
                "v0.50.1": "8c5c112b4563401d33b4da1dcd4d7f69db54e0e5",
            },
            "read_text_fn": lambda _url: 'const RELEASE_LIB_VERSION_TAG: &str = "v0.49.0";\n',
        }
        with self.assertRaisesRegex(ValueError, "allow_xls_pin_mismatch"):
            materialize_xls_bundle.resolve_archive_identity(**kwargs)

        identity = materialize_xls_bundle.resolve_archive_identity(
            allow_xls_pin_mismatch = True,
            **kwargs
        )
        self.assertEqual(identity["crate_implied_xls_release_tag"], "v0.49.0")
        self.assertEqual(identity["resolved_xls_release_tag"], "v0.50.1")

    def test_write_resolved_identity_is_stable_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            materialize_xls_bundle.write_resolved_identity(
                repo_root,
                {
                    "schema_version": 1,
                    "xls_pin": {
                        "kind": "release_tag",
                        "value": "v0.50.1",
                    },
                },
            )

            self.assertEqual(
                (repo_root / "resolved_identity.json").read_text(encoding = "utf-8"),
                """{
  "schema_version": 1,
  "xls_pin": {
    "kind": "release_tag",
    "value": "v0.50.1"
  }
}
""",
            )

    def test_materialize_runtime_surface_removes_stale_resolved_identity(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / "resolved_identity.json").write_text("stale\n", encoding = "utf-8")
            with mock.patch.object(
                materialize_xls_bundle,
                "resolve_materialization_inputs",
                return_value = {},
            ):
                with mock.patch.object(materialize_xls_bundle, "stage_runtime_payload"):
                    materialize_xls_bundle.materialize_runtime_surface(repo_root, {})

            self.assertFalse((repo_root / "resolved_identity.json").exists())

    def test_materialize_runtime_surface_rejects_private_filename_collision(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            with mock.patch.object(
                materialize_xls_bundle,
                "resolve_materialization_inputs",
                return_value = {
                    "runtime_files": [repo_root / "inputs" / "resolved_identity.json"],
                },
            ):
                with mock.patch.object(
                    materialize_xls_bundle,
                    "stage_runtime_payload",
                ) as mock_stage:
                    with self.assertRaisesRegex(ValueError, "reserved private filenames"):
                        materialize_xls_bundle.materialize_runtime_surface(repo_root, {})
            mock_stage.assert_not_called()

    def test_trusted_resolved_identity_requires_download_only_artifacts(self):
        materialize_xls_bundle.validate_resolved_identity_inputs(
            "download_only",
            "",
        )
        for artifact_source in ["auto", "installed_only", "local_paths"]:
            with self.subTest(artifact_source = artifact_source):
                with self.assertRaisesRegex(ValueError, "requires artifact_source=download_only"):
                    materialize_xls_bundle.validate_resolved_identity_inputs(
                        artifact_source,
                        "",
                    )

    def test_trusted_resolved_identity_rejects_local_aot_runtime_source(self):
        with self.assertRaisesRegex(
            ValueError,
            "cannot use local_xls_aot_runtime_source_path",
        ):
            materialize_xls_bundle.validate_resolved_identity_inputs(
                "download_only",
                "/tmp/review/xls-aot-runtime-source.tar.gz",
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
                "--no-self-update",
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
        self.assertEqual(env["CARGO_HOME"], "/tmp/xls-bundle-repo/_cargo_home/arm64")
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
            (download_root / "libxls_aot_runtime-arm64.a").write_text("", encoding = "utf-8")
            (download_root / "libxls_aot_runtime_link-arm64.toml").write_text("", encoding = "utf-8")
            (download_root / "xls-aot-runtime-source.tar.gz").write_text("", encoding = "utf-8")

            with mock.patch.object(materialize_xls_bundle, "detect_host_platform", return_value = "arm64"):
                with mock.patch.object(materialize_xls_bundle.subprocess, "run") as mock_run:
                    resolved = materialize_xls_bundle.download_versioned_artifacts(repo_root, "0.38.0")

            self.assertEqual(resolved["tools_root"], download_root)
            self.assertEqual(resolved["dslx_stdlib_root"], download_root / "xls" / "dslx" / "stdlib")
            self.assertEqual(
                resolved["libxls"],
                download_root / "libxls-v0.38.0-arm64.dylib",
            )
            self.assertEqual(
                resolved["xls_aot_runtime"],
                download_root / "libxls_aot_runtime-arm64.a",
            )
            self.assertEqual(
                resolved["xls_aot_runtime_link_config"],
                download_root / "libxls_aot_runtime_link-arm64.toml",
            )
            self.assertEqual(
                resolved["xls_aot_runtime_source"],
                download_root / "xls-aot-runtime-source.tar.gz",
            )
            self.assertEqual(resolved["runtime_files"], [])
            mock_run.assert_not_called()

    def test_download_versioned_artifacts_reuses_valid_cache_without_aot_runtime(self):
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

            self.assertIsNone(resolved["xls_aot_runtime"])
            self.assertIsNone(resolved["xls_aot_runtime_link_config"])
            self.assertIsNone(resolved["xls_aot_runtime_source"])
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

    def test_install_driver_uses_exact_git_revision(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            install_root = repo_root / "_cargo_driver" / "arm64" / revision
            with mock.patch.object(materialize_xls_bundle, "detect_host_platform", return_value = "arm64"):
                with mock.patch.object(materialize_xls_bundle.shutil, "which", return_value = "/usr/bin/rustup"):
                    with mock.patch.object(materialize_xls_bundle, "ensure_rustup_nightly_toolchain"):
                        with mock.patch.object(materialize_xls_bundle, "validate_installed_driver"):
                            with mock.patch.object(materialize_xls_bundle, "write_driver_git_provenance"):
                                with mock.patch.object(materialize_xls_bundle.subprocess, "run") as mock_run:
                                    materialize_xls_bundle.install_driver(
                                        repo_root = repo_root,
                                        driver_version = "",
                                        driver_git_revision = revision,
                                        libxls_path = "/tmp/xls-bundle/libxls.dylib" if sys.platform == "darwin" else "/tmp/xls-bundle/libxls.so",
                                        dslx_stdlib_path = "/tmp/xls-bundle",
                                    )

            mock_run.assert_called_once_with(
                [
                    "/usr/bin/rustup",
                    "run",
                    "nightly",
                    "cargo",
                    "install",
                    "--locked",
                    "--root",
                    str(install_root),
                    "--git",
                    "https://github.com/xlsynth/xlsynth-crate.git",
                    "--rev",
                    revision,
                    "xlsynth-driver",
                ],
                check = True,
                env = mock.ANY,
            )

    def test_git_driver_provenance_binds_revision_and_driver_bytes(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        with tempfile.TemporaryDirectory() as tempdir:
            driver_path = Path(tempdir) / "bin" / "xlsynth-driver"
            driver_path.parent.mkdir()
            driver_path.write_bytes(b"driver bytes")

            materialize_xls_bundle.write_driver_git_provenance(driver_path, revision)
            materialize_xls_bundle.validate_driver_git_provenance(driver_path, revision)

            driver_path.write_bytes(b"different driver bytes")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                materialize_xls_bundle.validate_driver_git_provenance(driver_path, revision)

    def test_git_driver_provenance_is_required_for_installed_revision(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        with tempfile.TemporaryDirectory() as tempdir:
            driver_path = Path(tempdir) / "bin" / "xlsynth-driver"
            driver_path.parent.mkdir()
            driver_path.write_bytes(b"driver bytes")

            with self.assertRaisesRegex(RuntimeError, "requires valid provenance"):
                materialize_xls_bundle.validate_driver_git_provenance(driver_path, revision)

    def test_installed_git_driver_materialization_requires_provenance(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            driver_path = root / "bin" / "xlsynth-driver"
            driver_path.parent.mkdir()
            driver_path.write_text("#!/bin/sh\nexit 0\n", encoding = "utf-8")
            driver_path.chmod(0o755)

            with self.assertRaisesRegex(RuntimeError, "requires valid provenance"):
                materialize_xls_bundle.materialize_driver_binary(
                    repo_root = root / "repo",
                    plan = {
                        "mode": "installed",
                        "driver": driver_path,
                        "driver_version": "",
                        "driver_git_revision": revision,
                    },
                    driver_output = root / "out" / "xlsynth-driver",
                    libxls_path = root / "runtime" / "libxls.so",
                    dslx_stdlib_path = root / "stdlib",
                )

    def test_installed_git_driver_materialization_accepts_matching_provenance(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            driver_path = root / "bin" / "xlsynth-driver"
            driver_path.parent.mkdir()
            driver_path.write_text("#!/bin/sh\nexit 0\n", encoding = "utf-8")
            driver_path.chmod(0o755)
            materialize_xls_bundle.write_driver_git_provenance(driver_path, revision)
            output_path = root / "out" / "xlsynth-driver"

            materialize_xls_bundle.materialize_driver_binary(
                repo_root = root / "repo",
                plan = {
                    "mode": "installed",
                    "driver": driver_path,
                    "driver_version": "",
                    "driver_git_revision": revision,
                },
                driver_output = output_path,
                libxls_path = root / "runtime" / "libxls.so",
                dslx_stdlib_path = root / "stdlib",
            )

            self.assertEqual(output_path.read_bytes(), driver_path.read_bytes())

    def test_auto_git_driver_materialization_reinstalls_without_provenance(self):
        revision = "0910ee19072a39a960b8df85b4f1e25199a4b4be"
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            declared_driver = root / "declared" / "xlsynth-driver"
            declared_driver.parent.mkdir()
            declared_driver.write_text("#!/bin/sh\nexit 0\n", encoding = "utf-8")
            declared_driver.chmod(0o755)
            fallback_driver = root / "fallback" / "xlsynth-driver"
            fallback_driver.parent.mkdir()
            fallback_driver.write_text("#!/bin/sh\nprintf 'fallback\\n'\n", encoding = "utf-8")
            fallback_driver.chmod(0o755)

            with mock.patch.object(
                materialize_xls_bundle,
                "install_driver",
                return_value = fallback_driver,
            ) as mock_install:
                materialize_xls_bundle.materialize_driver_binary(
                    repo_root = root / "repo",
                    plan = {
                        "mode": "auto_driver_input",
                        "driver": declared_driver,
                        "driver_version": "",
                        "driver_git_revision": revision,
                    },
                    driver_output = root / "out" / "xlsynth-driver",
                    libxls_path = root / "runtime" / "libxls.so",
                    dslx_stdlib_path = root / "stdlib",
                )

            mock_install.assert_called_once_with(
                root / "repo",
                "",
                root / "runtime" / "libxls.so",
                root / "stdlib",
                rustup_path = "",
                driver_git_revision = revision,
            )
            self.assertIn("fallback", (root / "out" / "xlsynth-driver").read_text(encoding = "utf-8"))

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
            xls_aot_runtime_path = input_root / "libxls_aot_runtime.a"
            xls_aot_runtime_path.write_text("aot\n", encoding = "utf-8")
            xls_aot_runtime_link_config_path = input_root / "libxls_aot_runtime_link.toml"
            xls_aot_runtime_link_config_path.write_text("format_version = 1\n", encoding = "utf-8")
            source_repo_root = input_root / "source_repo"
            source_repo_root.mkdir()
            (source_repo_root / "BUILD.bazel").write_text(
                'alias(name = "standalone_aot_runtime", actual = "//:dummy")\n',
                encoding = "utf-8",
            )
            xls_aot_runtime_source_path = input_root / "xls-aot-runtime-source.tar.gz"
            with tarfile.open(xls_aot_runtime_source_path, "w:gz") as archive:
                archive.add(source_repo_root / "BUILD.bazel", arcname = "BUILD.bazel")
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
                        "xls_aot_runtime": xls_aot_runtime_path,
                        "xls_aot_runtime_link_config": xls_aot_runtime_link_config_path,
                        "xls_aot_runtime_source": xls_aot_runtime_source_path,
                        "runtime_files": [runtime_companion],
                    },
                )

            metadata = dict(
                line.split("=", 1)
                for line in (repo_root / "runtime_metadata.txt").read_text(encoding = "utf-8").splitlines()
                if line
            )
            artifact_config = (repo_root / "xlsynth_artifact_config.toml").read_text(
                encoding = "utf-8"
            )
            self.assertEqual(metadata["libxls_name"], "libxls.so")
            self.assertEqual(metadata["xls_aot_runtime_name"], "libxls_aot_runtime.a")
            self.assertEqual(
                metadata["xls_aot_runtime_link_config_name"],
                "libxls_aot_runtime_link.toml",
            )
            self.assertEqual(metadata["xls_aot_runtime_source_repo"], "xls_aot_runtime_source")
            self.assertEqual(metadata["libxls_runtime_aliases"], "libxls-v0.38.0.so")
            self.assertEqual(metadata["libxls_runtime_files"], "libc++.so.1")
            self.assertIn('aot_runtime_path = "libxls_aot_runtime.a"', artifact_config)
            self.assertIn(
                'aot_runtime_link_config_path = "libxls_aot_runtime_link.toml"',
                artifact_config,
            )
            self.assertTrue((repo_root / "libxls_aot_runtime.a").is_file())
            self.assertTrue((repo_root / "libxls_aot_runtime_link.toml").is_file())
            self.assertTrue((repo_root / "xls_aot_runtime_source" / "BUILD.bazel").is_file())
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
            xls_aot_runtime_path = input_root / "libxls_aot_runtime.a"
            xls_aot_runtime_path.write_text("aot\n", encoding = "utf-8")
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
                    "xls_aot_runtime": xls_aot_runtime_path,
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

    def test_materialize_driver_binary_copies_local_driver_output(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            source_driver = repo_root / "input-driver"
            source_driver.write_text("#!/bin/sh\nexit 0\n", encoding = "utf-8")
            source_driver.chmod(0o755)
            driver_output = repo_root / "out" / "xlsynth-driver"
            libxls_path = repo_root / "libxls.so"
            libxls_path.write_text("xls\n", encoding = "utf-8")
            stdlib_root = repo_root / "stdlib"
            stdlib_root.mkdir()

            materialize_xls_bundle.materialize_driver_binary(
                repo_root,
                {
                    "mode": "local_paths",
                    "driver": source_driver,
                },
                driver_output,
                libxls_path,
                stdlib_root,
            )

            self.assertEqual(driver_output.read_text(encoding = "utf-8"), "#!/bin/sh\nexit 0\n")
            self.assertTrue(os.access(driver_output, os.X_OK))

    def test_driver_resolved_identity_must_match_selected_driver_pin(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            identity_input = root / "runtime_identity.json"
            identity_output = root / "driver_identity.json"
            identity_input.write_text(
                json.dumps({
                    "schema_version": 1,
                    "xlsynth_crate_pin": {
                        "kind": "release_tag",
                        "value": "v0.50.0",
                    },
                    "xls_pin": {
                        "kind": "release_tag",
                        "value": "v0.50.1",
                    },
                    "resolved_xlsynth_crate_revision": "a" * 40,
                    "crate_implied_xls_release_tag": "v0.50.1",
                    "resolved_xls_release_tag": "v0.50.1",
                    "resolved_xls_revision": "b" * 40,
                }),
                encoding = "utf-8",
            )
            plan = {
                "driver_version": "0.50.0",
            }

            materialize_xls_bundle.validate_and_copy_driver_resolved_identity(
                identity_input,
                identity_output,
                plan,
            )
            self.assertEqual(identity_output.read_bytes(), identity_input.read_bytes())

            plan["driver_version"] = "0.51.0"
            with self.assertRaisesRegex(ValueError, "does not match selected driver pin"):
                materialize_xls_bundle.validate_and_copy_driver_resolved_identity(
                    identity_input,
                    identity_output,
                    plan,
                )

    def test_driver_resolved_identity_rejects_incomplete_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            identity_input = root / "runtime_identity.json"
            identity_output = root / "driver_identity.json"
            identity_input.write_text(
                json.dumps({
                    "xlsynth_crate_pin": {
                        "kind": "release_tag",
                        "value": "v0.50.0",
                    },
                }),
                encoding = "utf-8",
            )

            with self.assertRaisesRegex(ValueError, "required schema fields"):
                materialize_xls_bundle.validate_and_copy_driver_resolved_identity(
                    identity_input,
                    identity_output,
                    {"driver_version": "0.50.0"},
                )

    def test_driver_resolved_identity_rejects_malformed_typed_values(self):
        valid_identity = {
            "schema_version": 1,
            "xlsynth_crate_pin": {
                "kind": "release_tag",
                "value": "v0.50.0",
            },
            "xls_pin": {
                "kind": "release_tag",
                "value": "v0.50.1",
            },
            "resolved_xlsynth_crate_revision": "a" * 40,
            "crate_implied_xls_release_tag": "v0.50.1",
            "resolved_xls_release_tag": "v0.50.1",
            "resolved_xls_revision": "b" * 40,
        }
        malformed_cases = [
            (
                "crate Git revision",
                {
                    **valid_identity,
                    "xlsynth_crate_pin": {
                        "kind": "git_revision",
                        "value": "A" * 40,
                    },
                },
                "lowercase exact SHA",
            ),
            (
                "XLS release pin",
                {
                    **valid_identity,
                    "xls_pin": {
                        "kind": "release_tag",
                        "value": "vnext",
                    },
                },
                "not an XLS release tag",
            ),
            (
                "resolved XLS release",
                {
                    **valid_identity,
                    "resolved_xls_release_tag": "vnext",
                },
                "not an XLS release tag",
            ),
        ]
        for label, identity, error in malformed_cases:
            with self.subTest(label):
                with tempfile.TemporaryDirectory() as tempdir:
                    root = Path(tempdir)
                    identity_input = root / "runtime_identity.json"
                    identity_output = root / "driver_identity.json"
                    identity_input.write_text(json.dumps(identity), encoding = "utf-8")

                    with self.assertRaisesRegex(ValueError, error):
                        materialize_xls_bundle.validate_and_copy_driver_resolved_identity(
                            identity_input,
                            identity_output,
                            {"driver_version": "0.50.0"},
                        )

    def test_driver_resolved_identity_rejects_contradictory_typed_values(self):
        crate_revision = "a" * 40
        xls_revision = "b" * 40
        valid_release_identity = {
            "schema_version": 1,
            "xlsynth_crate_pin": {
                "kind": "release_tag",
                "value": "v0.50.0",
            },
            "xls_pin": {
                "kind": "release_tag",
                "value": "v0.50.1",
            },
            "resolved_xlsynth_crate_revision": crate_revision,
            "crate_implied_xls_release_tag": "v0.50.1",
            "resolved_xls_release_tag": "v0.50.1",
            "resolved_xls_revision": xls_revision,
        }
        cases = [
            (
                {
                    **valid_release_identity,
                    "xls_pin": {
                        "kind": "git_revision",
                        "value": "c" * 40,
                    },
                },
                {"driver_version": "0.50.0"},
                "XLS Git pin",
            ),
            (
                {
                    **valid_release_identity,
                    "resolved_xls_release_tag": "v0.49.0",
                },
                {"driver_version": "0.50.0"},
                "XLS release pin",
            ),
            (
                {
                    **valid_release_identity,
                    "xlsynth_crate_pin": {
                        "kind": "git_revision",
                        "value": "c" * 40,
                    },
                },
                {"driver_git_revision": "c" * 40},
                "xlsynth-crate Git pin",
            ),
        ]
        for identity, plan, expected_error in cases:
            with self.subTest(expected_error):
                with tempfile.TemporaryDirectory() as tempdir:
                    root = Path(tempdir)
                    identity_input = root / "runtime_identity.json"
                    identity_output = root / "driver_identity.json"
                    identity_input.write_text(json.dumps(identity), encoding = "utf-8")

                    with self.assertRaisesRegex(ValueError, expected_error):
                        materialize_xls_bundle.validate_and_copy_driver_resolved_identity(
                            identity_input,
                            identity_output,
                            plan,
                        )

    def test_driver_resolved_identity_requires_explicit_xls_mismatch_override(self):
        identity = {
            "schema_version": 1,
            "xlsynth_crate_pin": {
                "kind": "release_tag",
                "value": "v0.36.0",
            },
            "xls_pin": {
                "kind": "release_tag",
                "value": "v0.40.0",
            },
            "resolved_xlsynth_crate_revision": "a" * 40,
            "crate_implied_xls_release_tag": "v0.39.0",
            "resolved_xls_release_tag": "v0.40.0",
            "resolved_xls_revision": "b" * 40,
        }
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            identity_input = root / "runtime_identity.json"
            identity_output = root / "driver_identity.json"
            identity_input.write_text(json.dumps(identity), encoding = "utf-8")

            with self.assertRaisesRegex(ValueError, "explicit development override"):
                materialize_xls_bundle.validate_and_copy_driver_resolved_identity(
                    identity_input,
                    identity_output,
                    {"driver_version": "0.36.0"},
                )
            materialize_xls_bundle.validate_and_copy_driver_resolved_identity(
                identity_input,
                identity_output,
                {"driver_version": "0.36.0"},
                allow_xls_pin_mismatch = True,
            )
            self.assertEqual(identity_output.read_bytes(), identity_input.read_bytes())


if __name__ == "__main__":
    unittest.main()
