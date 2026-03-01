# SPDX-License-Identifier: Apache-2.0

"""Materializes an XLS bundle repository for the rules_xlsynth module extension."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOL_BINARIES = [
    "dslx_interpreter_main",
    "ir_converter_main",
    "codegen_main",
    "opt_main",
    "prove_quickcheck_main",
    "typecheck_main",
    "dslx_fmt",
    "delay_info_main",
    "check_ir_equivalence_main",
]


def normalize_version(version):
    if not version:
        return version
    if version.startswith("v"):
        return version[1:]
    return version


def version_tag(version):
    return "v{}".format(normalize_version(version))


def libxls_name_for_platform(sys_platform):
    if sys_platform == "darwin":
        return "libxls.dylib"
    elif sys_platform == "linux":
        return "libxls.so"
    else:
        raise RuntimeError("Unsupported host platform: {}".format(sys_platform))


def derive_eda_tools_paths(xls_version, driver_version):
    normalized_xls_version = normalize_version(xls_version)
    normalized_driver_version = normalize_version(driver_version)
    tools_root = Path("/eda-tools/xlsynth/v{}".format(normalized_xls_version))
    return {
        "tools_root": tools_root,
        "dslx_stdlib_root": tools_root / "xls" / "dslx" / "stdlib",
        "driver": Path("/eda-tools/xlsynth-driver/{}/bin/xlsynth-driver".format(normalized_driver_version)),
        "libxls": tools_root / libxls_name_for_platform(sys.platform),
    }


def validate_stdlib_root(stdlib_root):
    if not stdlib_root.exists():
        raise ValueError("DSLX stdlib root does not exist: {}".format(stdlib_root))
    if not stdlib_root.is_dir():
        raise ValueError("DSLX stdlib root is not a directory: {}".format(stdlib_root))
    std_x = stdlib_root / "std.x"
    if not std_x.exists():
        raise ValueError("DSLX stdlib root must contain std.x directly: {}".format(stdlib_root))


def resolve_artifact_plan(
    artifact_source,
    xls_version,
    driver_version,
    local_tools_path = "",
    local_dslx_stdlib_path = "",
    local_driver_path = "",
    local_libxls_path = "",
    exists_fn = os.path.exists,
):
    if artifact_source == "local_paths":
        if xls_version or driver_version:
            raise ValueError("local_paths does not accept xls_version or xlsynth_driver_version")
        required = {
            "local_tools_path": local_tools_path,
            "local_dslx_stdlib_path": local_dslx_stdlib_path,
            "local_driver_path": local_driver_path,
            "local_libxls_path": local_libxls_path,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("local_paths requires {}".format(", ".join(sorted(missing))))
        return {
            "mode": "local_paths",
            "tools_root": Path(local_tools_path),
            "dslx_stdlib_root": Path(local_dslx_stdlib_path),
            "driver": Path(local_driver_path),
            "libxls": Path(local_libxls_path),
        }

    if artifact_source not in ("auto", "eda_tools_only", "download_only"):
        raise ValueError("Unknown artifact_source: {}".format(artifact_source))
    if not xls_version or not driver_version:
        raise ValueError("{} requires xls_version and xlsynth_driver_version".format(artifact_source))
    if local_tools_path or local_dslx_stdlib_path or local_driver_path or local_libxls_path:
        raise ValueError("{} does not accept local_paths attrs".format(artifact_source))

    eda_tools = derive_eda_tools_paths(xls_version, driver_version)
    if artifact_source == "download_only":
        return {
            "mode": "download",
            "xls_version": normalize_version(xls_version),
            "driver_version": normalize_version(driver_version),
        }

    eda_tools_present = all(exists_fn(str(path)) for path in eda_tools.values())
    if artifact_source == "auto" and eda_tools_present:
        return {
            "mode": "eda_tools",
            "tools_root": eda_tools["tools_root"],
            "dslx_stdlib_root": eda_tools["dslx_stdlib_root"],
            "driver": eda_tools["driver"],
            "libxls": eda_tools["libxls"],
        }
    if artifact_source == "eda_tools_only":
        if not eda_tools_present:
            raise ValueError(
                "eda_tools_only requires exact-version /eda-tools paths for XLS {} and driver {}".format(
                    normalize_version(xls_version),
                    normalize_version(driver_version),
                )
            )
        return {
            "mode": "eda_tools",
            "tools_root": eda_tools["tools_root"],
            "dslx_stdlib_root": eda_tools["dslx_stdlib_root"],
            "driver": eda_tools["driver"],
            "libxls": eda_tools["libxls"],
        }
    return {
        "mode": "download",
        "xls_version": normalize_version(xls_version),
        "driver_version": normalize_version(driver_version),
    }


def derive_runtime_library_path(libxls_path):
    return str(Path(libxls_path).parent)


def detect_host_platform():
    if sys.platform == "darwin":
        machine = os.uname().machine
        if machine == "arm64":
            return "arm64"
        if machine == "x86_64":
            return "x64"
        raise RuntimeError("Unsupported macOS architecture: {}".format(machine))

    if sys.platform != "linux":
        raise RuntimeError("Unsupported host platform: {}".format(sys.platform))

    machine = os.uname().machine
    if machine != "x86_64":
        raise RuntimeError("Unsupported Linux architecture: {}".format(machine))

    os_release_path = Path("/etc/os-release")
    if os_release_path.exists():
        os_release_data = os_release_path.read_text(encoding = "utf-8")
        lower = os_release_data.lower()
        if any(marker in lower for marker in ["rocky", "rhel", "almalinux", "centos"]):
            return "rocky8"
    return "ubuntu2004"


def ensure_clean_path(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def symlink_or_copy(src, dest):
    ensure_clean_path(dest)
    try:
        os.symlink(str(src), str(dest))
    except OSError:
        if src.is_dir():
            shutil.copytree(str(src), str(dest))
        else:
            shutil.copy2(str(src), str(dest))


def copy_path(src, dest):
    ensure_clean_path(dest)
    if src.is_dir():
        shutil.copytree(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest))


def link_stdlib_sources(stdlib_root, repo_root):
    validate_stdlib_root(stdlib_root)
    for child in stdlib_root.iterdir():
        if child.name.endswith(".x"):
            symlink_or_copy(child, repo_root / child.name)


def link_tool_binaries(tools_root, repo_root):
    for binary in TOOL_BINARIES:
        source = tools_root / binary
        if not source.exists():
            raise ValueError("Expected tool binary at {}".format(source))
        symlink_or_copy(source, repo_root / binary)


def normalized_libxls_name(libxls_path):
    suffix = Path(libxls_path).suffix
    if suffix == ".dylib":
        return "libxls.dylib"
    return "libxls.so"


def runtime_library_env_var(sys_platform):
    if sys_platform == "darwin":
        return "DYLD_LIBRARY_PATH"
    elif sys_platform == "linux":
        return "LD_LIBRARY_PATH"
    else:
        raise RuntimeError("Unsupported host platform: {}".format(sys_platform))


def prepend_search_path(path_value, existing_value):
    if existing_value:
        return "{}{}{}".format(path_value, os.pathsep, existing_value)
    return path_value


def build_driver_environment(
        libxls_path,
        dslx_stdlib_path,
        environ = None,
        sys_platform = sys.platform):
    env = dict(os.environ if environ == None else environ)
    runtime_library_path = str(Path(libxls_path).parent)
    runtime_var = runtime_library_env_var(sys_platform)
    env[runtime_var] = prepend_search_path(runtime_library_path, env.get(runtime_var, ""))
    env["XLS_DSO_PATH"] = str(libxls_path)
    env["DSLX_STDLIB_PATH"] = str(dslx_stdlib_path)
    return env


def patch_macos_dylib_install_name(dylib_path):
    if sys.platform == "darwin":
        subprocess.run(
            [
                "install_name_tool",
                "-id",
                str(dylib_path),
                str(dylib_path),
            ],
            check = True,
        )


def detect_driver_capability(driver_path, libxls_path, dslx_stdlib_path):
    env = build_driver_environment(libxls_path, dslx_stdlib_path)
    result = subprocess.run(
        [str(driver_path), "dslx2sv-types", "--help"],
        check = False,
        capture_output = True,
        text = True,
        env = env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to inspect xlsynth-driver capability at {}\nstdout:\n{}\nstderr:\n{}".format(
                driver_path,
                result.stdout,
                result.stderr,
            )
        )
    help_text = "{}\n{}".format(result.stdout, result.stderr)
    return "--sv_enum_case_naming_policy" in help_text


def build_driver_install_command(rustup_path, install_root, driver_version):
    return [
        rustup_path,
        "run",
        "nightly",
        "cargo",
        "install",
        "--locked",
        "--root",
        str(install_root),
        "--version",
        normalize_version(driver_version),
        "xlsynth-driver",
    ]


def build_rustup_toolchain_install_command(rustup_path):
    return [
        rustup_path,
        "toolchain",
        "install",
        "nightly",
        "--profile",
        "minimal",
    ]


def build_driver_install_environment(
        repo_root,
        libxls_path,
        dslx_stdlib_path,
        environ = None,
        sys_platform = sys.platform):
    env = build_driver_environment(
        libxls_path = libxls_path,
        dslx_stdlib_path = dslx_stdlib_path,
        environ = environ,
        sys_platform = sys_platform,
    )
    env["CARGO_HOME"] = str(repo_root / "_cargo_home")
    env["RUSTUP_HOME"] = str(repo_root / "_rustup_home")
    env["CARGO_TARGET_DIR"] = str(repo_root / "_cargo_target")
    return env


def ensure_rustup_nightly_toolchain(rustup_path, env):
    probe = subprocess.run(
        [rustup_path, "run", "nightly", "cargo", "--version"],
        check = False,
        capture_output = True,
        text = True,
        env = env,
    )
    if probe.returncode == 0:
        return
    subprocess.run(
        build_rustup_toolchain_install_command(rustup_path),
        check = True,
        env = env,
    )


def install_driver(repo_root, driver_version, libxls_path, dslx_stdlib_path):
    rustup = shutil.which("rustup")
    if rustup is None:
        raise RuntimeError(
            "rules_xlsynth download fallback requires rustup to install xlsynth-driver {}".format(
                driver_version
            )
        )

    install_root = repo_root / "_cargo_driver"
    cargo_home = repo_root / "_cargo_home"
    rustup_home = repo_root / "_rustup_home"
    target_root = repo_root / "_cargo_target"
    for path in [install_root, cargo_home, rustup_home, target_root]:
        ensure_clean_path(path)
        path.mkdir(parents = True, exist_ok = True)
    env = build_driver_install_environment(repo_root, libxls_path, dslx_stdlib_path)
    ensure_rustup_nightly_toolchain(rustup, env)
    subprocess.run(
        build_driver_install_command(rustup, install_root, driver_version),
        check = True,
        env = env,
    )
    driver_path = install_root / "bin" / "xlsynth-driver"
    result = subprocess.run(
        [str(driver_path), "--version"],
        check = False,
        capture_output = True,
        text = True,
        env = env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Installed xlsynth-driver is not runnable at {}\nstdout:\n{}\nstderr:\n{}".format(
                driver_path,
                result.stdout,
                result.stderr,
            )
        )
    return driver_path


def download_versioned_artifacts(repo_root, xls_version):
    script_path = Path(__file__).with_name("download_release.py")
    platform = detect_host_platform()
    download_root = repo_root / "_downloaded_xls"
    ensure_clean_path(download_root)
    download_root.mkdir(parents = True, exist_ok = True)
    subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--output",
            str(download_root),
            "--platform",
            platform,
            "--version",
            version_tag(xls_version),
            "--dso",
        ],
        check = True,
    )

    stdlib_root = download_root / "xls" / "dslx" / "stdlib"
    validate_stdlib_root(stdlib_root)
    libxls_candidates = sorted(download_root.glob("libxls-*.so")) + sorted(download_root.glob("libxls-*.dylib"))
    if len(libxls_candidates) != 1:
        raise RuntimeError("Expected exactly one libxls artifact in {}, found {}".format(download_root, libxls_candidates))
    return {
        "tools_root": download_root,
        "dslx_stdlib_root": stdlib_root,
        "libxls": libxls_candidates[0],
    }


def materialize_bundle(repo_root, plan):
    if plan["mode"] == "download":
        resolved = download_versioned_artifacts(repo_root, plan["xls_version"])
        link_tool_binaries(resolved["tools_root"], repo_root)
        link_stdlib_sources(resolved["dslx_stdlib_root"], repo_root)

        libxls_dest = repo_root / normalized_libxls_name(resolved["libxls"])
        copy_path(resolved["libxls"], libxls_dest)
        patch_macos_dylib_install_name(libxls_dest)

        driver_path = install_driver(
            repo_root,
            plan["driver_version"],
            libxls_dest,
            repo_root,
        )
        driver_dest = repo_root / "xlsynth-driver"
        symlink_or_copy(driver_path, driver_dest)
    else:
        resolved = plan
        validate_stdlib_root(resolved["dslx_stdlib_root"])
        link_tool_binaries(resolved["tools_root"], repo_root)
        link_stdlib_sources(resolved["dslx_stdlib_root"], repo_root)

        driver_dest = repo_root / "xlsynth-driver"
        symlink_or_copy(resolved["driver"], driver_dest)

        libxls_dest = repo_root / normalized_libxls_name(resolved["libxls"])
        symlink_or_copy(resolved["libxls"], libxls_dest)

    driver_supports = detect_driver_capability(driver_dest, libxls_dest, repo_root)
    metadata_path = repo_root / "bundle_metadata.txt"
    metadata_path.write_text(
        "".join([
            "driver_supports_sv_enum_case_naming_policy={}\n".format(
                "true" if driver_supports else "false"
            ),
            "libxls_name={}\n".format(libxls_dest.name),
        ]),
        encoding = "utf-8",
    )
    return {
        "driver_supports_sv_enum_case_naming_policy": driver_supports,
        "runtime_library_path": derive_runtime_library_path(libxls_dest),
        "libxls_name": libxls_dest.name,
    }


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required = True)
    parser.add_argument("--artifact-source", required = True)
    parser.add_argument("--xls-version", default = "")
    parser.add_argument("--xlsynth-driver-version", default = "")
    parser.add_argument("--local-tools-path", default = "")
    parser.add_argument("--local-dslx-stdlib-path", default = "")
    parser.add_argument("--local-driver-path", default = "")
    parser.add_argument("--local-libxls-path", default = "")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    repo_root.mkdir(parents = True, exist_ok = True)
    plan = resolve_artifact_plan(
        artifact_source = args.artifact_source,
        xls_version = args.xls_version,
        driver_version = args.xlsynth_driver_version,
        local_tools_path = args.local_tools_path,
        local_dslx_stdlib_path = args.local_dslx_stdlib_path,
        local_driver_path = args.local_driver_path,
        local_libxls_path = args.local_libxls_path,
    )
    materialize_bundle(repo_root, plan)


if __name__ == "__main__":
    main(sys.argv[1:])
