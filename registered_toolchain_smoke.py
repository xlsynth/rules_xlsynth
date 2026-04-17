# SPDX-License-Identifier: Apache-2.0
#
# This smoke suite exercises the registered-toolchain behavior that ChiliRT
# depends on. Each test creates a temporary Bazel workspace that registers
# @lazy_xls_toolchain, then checks the contract from a consumer's point of view:
# runtime-only targets and package loading may inspect toolchain metadata, but
# they must not install, compile, stage, or otherwise require xlsynth-driver.
# Tests that build @lazy_xls_toolchain//:xlsynth-driver are the explicit
# driver-user side of the same contract; they verify that driver materialization
# happens only for driver-backed targets and that local or installed driver
# files are declared Bazel action inputs.

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

import materialize_xls_bundle


BAZEL_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("REGISTERED_TOOLCHAIN_SMOKE_BAZEL_TIMEOUT", "240"))
RULES_XLSYNTH_REPO_ROOT = Path(
    os.environ.get("RULES_XLSYNTH_REPO_ROOT", Path(__file__).resolve().parent)
).resolve()


def rules_xlsynth_source_file(name):
    path = RULES_XLSYNTH_REPO_ROOT / name
    if not path.exists():
        raise RuntimeError("{} is missing from {}".format(name, RULES_XLSYNTH_REPO_ROOT))
    return path


def minimal_tool_path_env(bazel_path):
    path_dirs = [str(Path(bazel_path).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return os.pathsep.join(path_dirs)


def write_text_file(path, content, mode = None):
    path.write_text(content, encoding = "utf-8")
    if mode != None:
        path.chmod(mode)


def copy_runfile(source_name, dest):
    shutil.copy2(rules_xlsynth_source_file(source_name), dest)


def create_minimal_rules_xlsynth_repo(repo_root):
    repo_root.mkdir()
    write_text_file(
        repo_root / "MODULE.bazel",
        """
module(name = "rules_xlsynth")

bazel_dep(name = "bazel_skylib", version = "1.6.1")
bazel_dep(name = "rules_cc", version = "0.2.11")
""".lstrip(),
    )
    write_text_file(
        repo_root / "BUILD.bazel",
        """
exports_files(["materialize_xls_bundle.py"])

toolchain_type(
    name = "toolchain_type",
    visibility = ["//visibility:public"],
)
""".lstrip(),
    )
    copy_runfile("extensions.bzl", repo_root / "extensions.bzl")
    copy_runfile("xls_toolchain.bzl", repo_root / "xls_toolchain.bzl")
    copy_runfile("materialize_xls_bundle.py", repo_root / "materialize_xls_bundle.py")


def build_minimal_shared_library(output_path):
    source_path = output_path.with_suffix(".c")
    write_text_file(source_path, "int rules_xlsynth_runtime_probe(void) { return 0; }\n")

    if sys.platform == "darwin":
        command = [
            "cc",
            "-dynamiclib",
            "-install_name",
            "@rpath/{}".format(output_path.name),
            "-o",
            str(output_path),
            str(source_path),
        ]
    else:
        command = [
            "cc",
            "-shared",
            "-fPIC",
            "-Wl,-soname,{}".format(output_path.name),
            "-o",
            str(output_path),
            str(source_path),
        ]
    subprocess.run(command, check = True)


def create_local_runtime_bundle(root):
    tools_root = root / "tools"
    stdlib_root = root / "stdlib"
    tools_root.mkdir(parents = True)
    stdlib_root.mkdir(parents = True)
    write_text_file(stdlib_root / "std.x", "pub fn id(x: u1) -> u1 { x }\n")
    for tool_name in materialize_xls_bundle.TOOL_BINARIES:
        write_text_file(tools_root / tool_name, "#!/bin/sh\nexit 127\n", 0o755)

    libxls_name = "libxls.dylib" if sys.platform == "darwin" else "libxls.so"
    libxls_path = root / libxls_name
    build_minimal_shared_library(libxls_path)
    return {
        "tools_root": tools_root,
        "stdlib_root": stdlib_root,
        "libxls_path": libxls_path,
    }


def create_installed_runtime_bundle(installed_tools_root_prefix, xls_version):
    installed_version_root = installed_tools_root_prefix / "v{}".format(xls_version)
    stdlib_root = installed_version_root / "xls" / "dslx" / "stdlib"
    installed_version_root.mkdir(parents = True)
    stdlib_root.mkdir(parents = True)
    write_text_file(stdlib_root / "std.x", "pub fn id(x: u1) -> u1 { x }\n")
    for tool_name in materialize_xls_bundle.TOOL_BINARIES:
        write_text_file(installed_version_root / tool_name, "#!/bin/sh\nexit 127\n", 0o755)

    libxls_name = "libxls.dylib" if sys.platform == "darwin" else "libxls.so"
    libxls_path = installed_version_root / libxls_name
    build_minimal_shared_library(libxls_path)
    return {
        "installed_tools_root_prefix": installed_tools_root_prefix,
        "tools_root": installed_version_root,
        "stdlib_root": stdlib_root,
        "libxls_path": libxls_path,
    }


def installed_driver_path(installed_driver_root_prefix, driver_version):
    return installed_driver_root_prefix / driver_version / "bin" / "xlsynth-driver"


def write_versioned_driver(path, marker, driver_version = "0.33.0"):
    write_text_file(
        path,
        """#!/bin/sh
if [ "${{1:-}}" = "--version" ]; then
  printf 'xlsynth-driver {driver_version} {marker}\\n'
  exit 0
fi
printf 'unexpected fake driver execution {marker}\\n' >&2
exit 1
""".format(driver_version = driver_version, marker = marker),
        0o755,
    )


def create_runtime_only_workspace(workspace_root, rules_xlsynth_root, local_bundle, local_driver_path = None):
    workspace_root.mkdir()
    local_driver_attr = "" if local_driver_path == None else """
    local_driver_path = "{local_driver_path}",
""".format(local_driver_path = local_driver_path)
    write_text_file(
        workspace_root / "MODULE.bazel",
        """
module(name = "registered_runtime_only")

bazel_dep(name = "rules_xlsynth", version = "0.0.0")
local_path_override(
    module_name = "rules_xlsynth",
    path = "{rules_xlsynth_root}",
)

xls = use_extension("@rules_xlsynth//:extensions.bzl", "xls")
xls.toolchain(
    name = "lazy_xls",
    artifact_source = "local_paths",
    local_tools_path = "{tools_root}",
    local_dslx_stdlib_path = "{stdlib_root}",
    local_libxls_path = "{libxls_path}",
{local_driver_attr}
)
use_repo(
    xls,
    "lazy_xls_runtime",
    "lazy_xls_toolchain",
)
register_toolchains("@lazy_xls_toolchain//:all")
""".format(
            rules_xlsynth_root = rules_xlsynth_root,
            tools_root = local_bundle["tools_root"],
            stdlib_root = local_bundle["stdlib_root"],
            libxls_path = local_bundle["libxls_path"],
            local_driver_attr = local_driver_attr,
        ).lstrip(),
    )
    write_text_file(
        workspace_root / "BUILD.bazel",
        """
filegroup(
    name = "runtime_inputs",
    srcs = ["@lazy_xls_runtime//:xlsynth_sys_runtime_files"],
)
""".lstrip(),
    )


def create_auto_installed_workspace(
        workspace_root,
        rules_xlsynth_root,
        local_bundle,
        installed_driver_root_prefix,
        xls_version = "0.38.0",
        driver_version = "0.33.0"):
    workspace_root.mkdir()
    write_text_file(
        workspace_root / "MODULE.bazel",
        """
module(name = "auto_installed_toolchain")

bazel_dep(name = "rules_xlsynth", version = "0.0.0")
local_path_override(
    module_name = "rules_xlsynth",
    path = "{rules_xlsynth_root}",
)

xls = use_extension("@rules_xlsynth//:extensions.bzl", "xls")
xls.toolchain(
    name = "lazy_xls",
    artifact_source = "auto",
    xls_version = "{xls_version}",
    xlsynth_driver_version = "{driver_version}",
    installed_tools_root_prefix = "{installed_tools_root_prefix}",
    installed_driver_root_prefix = "{installed_driver_root_prefix}",
)
use_repo(
    xls,
    "lazy_xls_runtime",
    "lazy_xls_toolchain",
)
register_toolchains("@lazy_xls_toolchain//:all")
""".format(
            driver_version = driver_version,
            installed_driver_root_prefix = installed_driver_root_prefix,
            installed_tools_root_prefix = local_bundle["installed_tools_root_prefix"],
            rules_xlsynth_root = rules_xlsynth_root,
            xls_version = xls_version,
        ).lstrip(),
    )
    write_text_file(workspace_root / "BUILD.bazel", "")


def run_nested_bazel(bazel_path, output_user_root, workspace_root, env, args):
    cmdline = [
        bazel_path,
        "--bazelrc=/dev/null",
        "--max_idle_secs=5",
        "--output_user_root={}".format(output_user_root),
    ] + args
    print("Running nested workspace command: " + subprocess.list2cmdline(cmdline), flush = True)
    return subprocess.run(
        cmdline,
        cwd = workspace_root,
        env = env,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        universal_newlines = True,
        check = False,
        timeout = BAZEL_COMMAND_TIMEOUT_SECONDS,
    )


def query_single_output_file(bazel_path, output_user_root, workspace_root, env, label):
    result = run_nested_bazel(
        bazel_path,
        output_user_root,
        workspace_root,
        env,
        ["cquery", label, "--output=files"],
    )
    combined_output = "{}\n{}".format(result.stdout, result.stderr)
    if result.returncode != 0:
        raise RuntimeError(combined_output)
    outputs = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    if len(outputs) != 1:
        raise RuntimeError("Expected one output for {}, got {}\n{}".format(label, outputs, combined_output))
    output_path = Path(outputs[0])
    if output_path.is_absolute():
        return output_path
    return workspace_root / output_path


def paths_with_basename(root, basename):
    return sorted(path for path in root.rglob(basename))


class RegisteredRuntimeOnlyTest(unittest.TestCase):
    def create_nested_workspace(self, root, local_driver_path = None):
        rules_xlsynth_root = root / "rules_xlsynth"
        create_minimal_rules_xlsynth_repo(rules_xlsynth_root)
        local_bundle = create_local_runtime_bundle(root / "local_xls")
        workspace_root = root / "workspace"
        create_runtime_only_workspace(workspace_root, rules_xlsynth_root, local_bundle, local_driver_path)
        return workspace_root

    def test_00_registered_toolchain_does_not_require_driver_for_runtime_files(self):
        bazel_path = shutil.which("bazel")
        if bazel_path == None:
            self.skipTest("bazel is not on PATH")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace_root = self.create_nested_workspace(root)
            env = dict(os.environ)
            env["PATH"] = minimal_tool_path_env(bazel_path)
            output_user_root = root / "bazel_output_user_root"
            result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["build", "//:runtime_inputs"],
            )

        combined_output = "{}\n{}".format(result.stdout, result.stderr)
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertNotIn("xlsynth-driver", combined_output)
        self.assertNotIn("rustup", combined_output)
        self.assertNotIn("cargo", combined_output.lower())

    def test_03_local_paths_without_driver_path_fails_when_driver_is_built(self):
        bazel_path = shutil.which("bazel")
        if bazel_path == None:
            self.skipTest("bazel is not on PATH")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace_root = self.create_nested_workspace(root)
            env = dict(os.environ)
            env["PATH"] = minimal_tool_path_env(bazel_path)
            output_user_root = root / "bazel_output_user_root"
            result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["build", "@lazy_xls_toolchain//:xlsynth-driver"],
            )

        combined_output = "{}\n{}".format(result.stdout, result.stderr)
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("local_paths driver materialization requires local_driver_path", combined_output)

    def test_03_local_driver_file_is_declared_action_input(self):
        bazel_path = shutil.which("bazel")
        if bazel_path == None:
            self.skipTest("bazel is not on PATH")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            local_driver = root / "local_driver" / "xlsynth-driver"
            local_driver.parent.mkdir()
            write_text_file(local_driver, "#!/bin/sh\n# version-one\n", 0o755)
            workspace_root = self.create_nested_workspace(root, local_driver)
            env = dict(os.environ)
            env["PATH"] = minimal_tool_path_env(bazel_path)
            output_user_root = root / "bazel_output_user_root"

            first_result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["build", "@lazy_xls_toolchain//:xlsynth-driver"],
            )
            self.assertEqual(first_result.returncode, 0, "{}\n{}".format(first_result.stdout, first_result.stderr))
            driver_output = query_single_output_file(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                "@lazy_xls_toolchain//:xlsynth-driver",
            )
            self.assertEqual(driver_output.read_text(encoding = "utf-8"), "#!/bin/sh\n# version-one\n")

            write_text_file(local_driver, "#!/bin/sh\n# version-two\n", 0o755)
            second_result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["build", "@lazy_xls_toolchain//:xlsynth-driver"],
            )
            self.assertEqual(second_result.returncode, 0, "{}\n{}".format(second_result.stdout, second_result.stderr))
            self.assertEqual(driver_output.read_text(encoding = "utf-8"), "#!/bin/sh\n# version-two\n")

    def test_04_auto_installed_driver_file_is_declared_action_input(self):
        bazel_path = shutil.which("bazel")
        if bazel_path == None:
            self.skipTest("bazel is not on PATH")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            driver_version = "0.33.0"
            installed_driver_root_prefix = root / "installed_driver"
            installed_driver = installed_driver_path(installed_driver_root_prefix, driver_version)
            installed_driver.parent.mkdir(parents = True)
            write_versioned_driver(installed_driver, "version-one", driver_version)

            rules_xlsynth_root = root / "rules_xlsynth"
            create_minimal_rules_xlsynth_repo(rules_xlsynth_root)
            local_bundle = create_installed_runtime_bundle(root / "installed_tools", "0.38.0")
            workspace_root = root / "workspace"
            create_auto_installed_workspace(
                workspace_root,
                rules_xlsynth_root,
                local_bundle,
                installed_driver_root_prefix,
                driver_version = driver_version,
            )
            env = dict(os.environ)
            env["PATH"] = minimal_tool_path_env(bazel_path)
            output_user_root = root / "bazel_output_user_root"

            first_result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["build", "@lazy_xls_toolchain//:xlsynth-driver"],
            )
            self.assertEqual(first_result.returncode, 0, "{}\n{}".format(first_result.stdout, first_result.stderr))
            driver_output = query_single_output_file(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                "@lazy_xls_toolchain//:xlsynth-driver",
            )
            self.assertIn("version-one", driver_output.read_text(encoding = "utf-8"))

            write_versioned_driver(installed_driver, "version-two", driver_version)
            second_result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["build", "@lazy_xls_toolchain//:xlsynth-driver"],
            )
            self.assertEqual(second_result.returncode, 0, "{}\n{}".format(second_result.stdout, second_result.stderr))
            driver_text = driver_output.read_text(encoding = "utf-8")
            self.assertIn("version-two", driver_text)
            self.assertNotIn("version-one", driver_text)

    def test_02_auto_installed_toolchain_load_does_not_stage_host_driver(self):
        bazel_path = shutil.which("bazel")
        if bazel_path == None:
            self.skipTest("bazel is not on PATH")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            driver_version = "0.33.0"
            installed_driver_root_prefix = root / "installed_driver"
            installed_driver = installed_driver_path(installed_driver_root_prefix, driver_version)
            installed_driver.parent.mkdir(parents = True)
            write_versioned_driver(installed_driver, "version-one", driver_version)

            rules_xlsynth_root = root / "rules_xlsynth"
            create_minimal_rules_xlsynth_repo(rules_xlsynth_root)
            local_bundle = create_installed_runtime_bundle(root / "installed_tools", "0.38.0")
            workspace_root = root / "workspace"
            create_auto_installed_workspace(
                workspace_root,
                rules_xlsynth_root,
                local_bundle,
                installed_driver_root_prefix,
                driver_version = driver_version,
            )
            env = dict(os.environ)
            env["PATH"] = minimal_tool_path_env(bazel_path)
            output_user_root = root / "bazel_output_user_root"
            result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["query", "@lazy_xls_toolchain//:all"],
            )

            staged_host_drivers = paths_with_basename(output_user_root, "host_xlsynth-driver")

        combined_output = "{}\n{}".format(result.stdout, result.stderr)
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("@lazy_xls_toolchain//:xlsynth-driver", combined_output)
        self.assertEqual(staged_host_drivers, [])

    def test_01_toolchain_package_load_does_not_materialize_driver(self):
        bazel_path = shutil.which("bazel")
        if bazel_path == None:
            self.skipTest("bazel is not on PATH")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace_root = self.create_nested_workspace(root)
            env = dict(os.environ)
            env["PATH"] = minimal_tool_path_env(bazel_path)
            output_user_root = root / "bazel_output_user_root"
            result = run_nested_bazel(
                bazel_path,
                output_user_root,
                workspace_root,
                env,
                ["query", "@lazy_xls_toolchain//:all"],
            )

        combined_output = "{}\n{}".format(result.stdout, result.stderr)
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("@lazy_xls_toolchain//:xlsynth-driver", combined_output)
        self.assertNotIn("Installing xlsynth-driver", combined_output)
        self.assertNotIn("Compiling xlsynth-driver", combined_output)
        self.assertNotIn("rustup", combined_output)
        self.assertNotIn("cargo", combined_output.lower())


if __name__ == "__main__":
    unittest.main()
