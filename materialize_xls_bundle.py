# SPDX-License-Identifier: Apache-2.0

"""Materializes an XLS bundle repository for the rules_xlsynth module extension."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOL_BINARIES = [
    "dslx_interpreter_main",
    "ir_converter_main",
    "block_to_verilog_main",
    "codegen_main",
    "opt_main",
    "prove_quickcheck_main",
    "typecheck_main",
    "dslx_fmt",
    "delay_info_main",
    "check_ir_equivalence_main",
]

_DRIVER_CAPABILITY_FLAGS = {
    "driver_supports_sv_enum_case_naming_policy": "--sv_enum_case_naming_policy",
    "driver_supports_sv_struct_field_ordering": "--sv_struct_field_ordering",
}


def run_captured_text_command(args, check, env = None):
    return subprocess.run(
        args,
        check = check,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        universal_newlines = True,
        env = env,
    )


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


def derive_installed_paths(
        xls_version,
        driver_version,
        installed_tools_root_prefix,
        installed_driver_root_prefix,
        sys_platform = sys.platform):
    normalized_xls_version = normalize_version(xls_version)
    normalized_driver_version = normalize_version(driver_version)
    tools_root = Path(installed_tools_root_prefix) / "v{}".format(normalized_xls_version)
    return {
        "tools_root": tools_root,
        "dslx_stdlib_root": tools_root / "xls" / "dslx" / "stdlib",
        "driver": Path(installed_driver_root_prefix) / normalized_driver_version / "bin" / "xlsynth-driver",
        "libxls": tools_root / libxls_name_for_platform(sys_platform),
    }


def derive_installed_runtime_paths(
        xls_version,
        installed_tools_root_prefix,
        sys_platform = sys.platform):
    normalized_xls_version = normalize_version(xls_version)
    tools_root = Path(installed_tools_root_prefix) / "v{}".format(normalized_xls_version)
    return {
        "tools_root": tools_root,
        "dslx_stdlib_root": tools_root / "xls" / "dslx" / "stdlib",
        "libxls": tools_root / libxls_name_for_platform(sys_platform),
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
    surface = "toolchain",
    installed_tools_root_prefix = "",
    installed_driver_root_prefix = "",
    local_tools_path = "",
    local_dslx_stdlib_path = "",
    local_driver_path = "",
    local_libxls_path = "",
    exists_fn = os.path.exists,
):
    if surface not in ("runtime", "toolchain"):
        raise ValueError("Unknown XLS bundle surface: {}".format(surface))
    include_driver = surface == "toolchain"

    if artifact_source == "local_paths":
        if xls_version or driver_version:
            raise ValueError("local_paths does not accept xls_version or xlsynth_driver_version")
        required = {
            "local_tools_path": local_tools_path,
            "local_dslx_stdlib_path": local_dslx_stdlib_path,
            "local_libxls_path": local_libxls_path,
        }
        if include_driver:
            required["local_driver_path"] = local_driver_path
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("local_paths requires {}".format(", ".join(sorted(missing))))
        plan = {
            "mode": "local_paths",
            "tools_root": Path(local_tools_path),
            "dslx_stdlib_root": Path(local_dslx_stdlib_path),
            "libxls": Path(local_libxls_path),
        }
        if include_driver:
            plan["driver"] = Path(local_driver_path)
        return plan

    if artifact_source not in ("auto", "installed_only", "download_only"):
        raise ValueError("Unknown artifact_source: {}".format(artifact_source))
    if not xls_version:
        raise ValueError("{} requires xls_version".format(artifact_source))
    if include_driver and not driver_version:
        raise ValueError("{} toolchain surface requires xlsynth_driver_version".format(artifact_source))
    if local_tools_path or local_dslx_stdlib_path or local_driver_path or local_libxls_path:
        raise ValueError("{} does not accept local_paths attrs".format(artifact_source))
    if artifact_source == "download_only":
        if installed_tools_root_prefix or installed_driver_root_prefix:
            raise ValueError("download_only does not accept installed_* attrs")
    else:
        required_installed = {"installed_tools_root_prefix": installed_tools_root_prefix}
        if include_driver:
            required_installed["installed_driver_root_prefix"] = installed_driver_root_prefix
        missing_installed = [name for name, value in required_installed.items() if not value]
        if missing_installed:
            raise ValueError("{} requires {}".format(artifact_source, ", ".join(sorted(missing_installed))))

    if include_driver:
        installed_paths = derive_installed_paths(
            xls_version = xls_version,
            driver_version = driver_version,
            installed_tools_root_prefix = installed_tools_root_prefix,
            installed_driver_root_prefix = installed_driver_root_prefix,
        )
    else:
        installed_paths = derive_installed_runtime_paths(
            xls_version = xls_version,
            installed_tools_root_prefix = installed_tools_root_prefix,
        )

    if artifact_source == "download_only":
        plan = {
            "mode": "download",
            "xls_version": normalize_version(xls_version),
        }
        if include_driver:
            plan["driver_version"] = normalize_version(driver_version)
        return plan

    installed_paths_present = all(exists_fn(str(path)) for path in installed_paths.values())
    if artifact_source == "auto" and installed_paths_present:
        plan = {
            "mode": "installed",
            "tools_root": installed_paths["tools_root"],
            "dslx_stdlib_root": installed_paths["dslx_stdlib_root"],
            "libxls": installed_paths["libxls"],
        }
        if include_driver:
            plan["driver"] = installed_paths["driver"]
        return plan
    if artifact_source == "installed_only":
        if not installed_paths_present:
            message = "installed_only requires exact-version installed paths for XLS {}".format(
                normalize_version(xls_version),
            )
            if include_driver:
                message = "{} and driver {}".format(message, normalize_version(driver_version))
            raise ValueError(message)
        plan = {
            "mode": "installed",
            "tools_root": installed_paths["tools_root"],
            "dslx_stdlib_root": installed_paths["dslx_stdlib_root"],
            "libxls": installed_paths["libxls"],
        }
        if include_driver:
            plan["driver"] = installed_paths["driver"]
        return plan
    plan = {
        "mode": "download",
        "xls_version": normalize_version(xls_version),
    }
    if include_driver:
        plan["driver_version"] = normalize_version(driver_version)
    return plan


def resolve_driver_plan(
    artifact_source,
    driver_version,
    installed_driver_root_prefix = "",
    local_driver_path = "",
    driver_input = "",
    exists_fn = os.path.exists,
):
    if artifact_source == "local_paths":
        if not local_driver_path:
            raise ValueError("local_paths driver materialization requires local_driver_path")
        if driver_input:
            resolved_driver_input = Path(driver_input).resolve()
            resolved_local_driver_path = Path(local_driver_path).resolve()
            if resolved_driver_input != resolved_local_driver_path:
                raise ValueError(
                    "local_paths declared driver input must match local_driver_path: {} != {}".format(
                        driver_input,
                        local_driver_path,
                    )
                )
            return {
                "mode": "local_paths",
                "driver": Path(driver_input),
            }
        return {
            "mode": "local_paths",
            "driver": Path(local_driver_path),
        }

    if driver_input:
        if artifact_source == "auto":
            if not driver_version:
                raise ValueError("auto declared driver input requires xlsynth_driver_version")
            return {
                "mode": "auto_driver_input",
                "driver": Path(driver_input),
                "driver_version": normalize_version(driver_version),
                "installed_driver_root_prefix": installed_driver_root_prefix,
            }
        if artifact_source in ("auto", "installed_only"):
            if not driver_version:
                raise ValueError("{} declared driver input requires xlsynth_driver_version".format(artifact_source))
            return {
                "mode": "installed",
                "driver": Path(driver_input),
                "driver_version": normalize_version(driver_version),
            }
        if artifact_source == "download_only":
            raise ValueError("download_only driver materialization does not accept driver_input")
        raise ValueError("Unknown artifact_source: {}".format(artifact_source))

    if artifact_source not in ("auto", "installed_only", "download_only"):
        raise ValueError("Unknown artifact_source: {}".format(artifact_source))
    if not driver_version:
        raise ValueError("{} driver materialization requires xlsynth_driver_version".format(artifact_source))
    if artifact_source == "download_only":
        if installed_driver_root_prefix:
            raise ValueError("download_only driver materialization does not accept installed_driver_root_prefix")
        return {
            "mode": "download",
            "driver_version": normalize_version(driver_version),
        }

    if not installed_driver_root_prefix:
        raise ValueError("{} driver materialization requires installed_driver_root_prefix".format(artifact_source))

    normalized_driver_version = normalize_version(driver_version)
    installed_driver = Path(installed_driver_root_prefix) / normalized_driver_version / "bin" / "xlsynth-driver"
    if exists_fn(str(installed_driver)):
        return {
            "mode": "installed",
            "driver": installed_driver,
            "driver_version": normalized_driver_version,
        }
    if artifact_source == "installed_only":
        raise ValueError(
            "installed_only driver materialization requires installed path for driver {}".format(
                normalized_driver_version,
            )
        )
    return {
        "mode": "download",
        "driver_version": normalized_driver_version,
    }


def derive_runtime_library_path(libxls_path):
    return str(Path(libxls_path).parent)


def load_runtime_manifest(search_root):
    manifest_paths = sorted(Path(search_root).glob("libxls-runtime-*-manifest.json"))
    if not manifest_paths:
        return []
    if len(manifest_paths) != 1:
        raise RuntimeError(
            "Expected at most one runtime manifest in {}, found {}".format(
                search_root,
                manifest_paths,
            )
        )
    manifest = json.loads(manifest_paths[0].read_text(encoding = "utf-8"))
    runtime_files = manifest.get("runtime_files", [])
    if not isinstance(runtime_files, list) or not all(isinstance(name, str) and name for name in runtime_files):
        raise RuntimeError("Invalid runtime manifest at {}".format(manifest_paths[0]))
    resolved_paths = []
    for runtime_file in runtime_files:
        runtime_path = Path(search_root) / runtime_file
        if not runtime_path.exists():
            raise RuntimeError(
                "Runtime manifest {} references missing file {}".format(
                    manifest_paths[0],
                    runtime_path,
                )
            )
        resolved_paths.append(runtime_path)
    return resolved_paths


def detect_host_platform():
    if sys.platform == "darwin":
        machine = os.uname().machine
        if machine == "arm64":
            return "arm64"
        if machine == "x86_64":
            raise RuntimeError(
                "download-backed XLS bundles do not support Intel macOS because the xlsynth "
                "releases do not publish matching x86_64 Darwin artifacts"
            )
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


def driver_install_root(repo_root, driver_version, host_platform):
    return repo_root / "_cargo_driver" / host_platform / normalize_version(driver_version)


def rustup_home_root(repo_root, host_platform):
    return repo_root / "_rustup_home" / host_platform


def cargo_target_root(repo_root, host_platform):
    return repo_root / "_cargo_target" / host_platform


def downloaded_xls_root(repo_root, xls_version, host_platform):
    return repo_root / "_downloaded_xls" / host_platform / normalize_version(xls_version)


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


def parse_readelf_soname(stdout):
    marker = "Library soname: ["
    for line in stdout.splitlines():
        if marker not in line:
            continue
        return line.split(marker, 1)[1].split("]", 1)[0]
    return ""


def read_linux_soname(libxls_path):
    result = run_captured_text_command(
        ["readelf", "-d", str(libxls_path)],
        check = False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to inspect ELF SONAME at {}\nstdout:\n{}\nstderr:\n{}".format(
                libxls_path,
                result.stdout,
                result.stderr,
            )
    )
    return parse_readelf_soname(result.stdout)


def materialize_runtime_library_aliases(libxls_path, runtime_aliases):
    staged_aliases = []
    for alias in runtime_aliases:
        if not alias or alias == Path(libxls_path).name:
            continue
        alias_path = Path(libxls_path).parent / alias
        ensure_clean_path(alias_path)
        try:
            os.symlink(Path(libxls_path).name, str(alias_path))
        except OSError:
            shutil.copy2(str(libxls_path), str(alias_path))
        staged_aliases.append(alias)
    return staged_aliases


def normalize_linux_soname(libxls_path):
    soname = read_linux_soname(libxls_path)
    expected = Path(libxls_path).name
    if not soname or soname == expected:
        return []

    patchelf = shutil.which("patchelf")
    if patchelf == None:
        return materialize_runtime_library_aliases(libxls_path, [soname])

    subprocess.run(
        [patchelf, "--set-soname", expected, str(libxls_path)],
        check = True,
    )
    return []


def normalize_runtime_library_identity(libxls_path, sys_platform = sys.platform):
    if sys_platform == "darwin":
        subprocess.run(
            [
                "install_name_tool",
                "-id",
                "@rpath/{}".format(Path(libxls_path).name),
                str(libxls_path),
            ],
            check = True,
        )
        return []
    elif sys_platform == "linux":
        return normalize_linux_soname(libxls_path)
    else:
        raise RuntimeError("Unsupported host platform: {}".format(sys_platform))


def detect_driver_capabilities(driver_path, libxls_path, dslx_stdlib_path):
    env = build_driver_environment(libxls_path, dslx_stdlib_path)
    result = run_captured_text_command(
        [str(driver_path), "dslx2sv-types", "--help"],
        check = False,
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
    return {
        capability_name: capability_flag in help_text
        for capability_name, capability_flag in _DRIVER_CAPABILITY_FLAGS.items()
    }


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
        sys_platform = sys.platform,
        host_platform = ""):
    env = build_driver_environment(
        libxls_path = libxls_path,
        dslx_stdlib_path = dslx_stdlib_path,
        environ = environ,
        sys_platform = sys_platform,
    )
    resolved_host_platform = host_platform or detect_host_platform()
    env["RUSTUP_HOME"] = str(rustup_home_root(repo_root, resolved_host_platform))
    env["CARGO_TARGET_DIR"] = str(cargo_target_root(repo_root, resolved_host_platform))
    return env


def ensure_rustup_nightly_toolchain(rustup_path, env):
    probe = run_captured_text_command(
        [rustup_path, "run", "nightly", "cargo", "--version"],
        check = False,
        env = env,
    )
    if probe.returncode == 0:
        return
    subprocess.run(
        build_rustup_toolchain_install_command(rustup_path),
        check = True,
        env = env,
    )


def validate_installed_driver(driver_path, env, driver_version):
    try:
        result = run_captured_text_command(
            [str(driver_path), "--version"],
            check = False,
            env = env,
        )
    except OSError as error:
        raise RuntimeError("Failed to execute installed xlsynth-driver at {}: {}".format(driver_path, error)) from error
    if result.returncode != 0:
        raise RuntimeError(
            "Installed xlsynth-driver is not runnable at {}\nstdout:\n{}\nstderr:\n{}".format(
                driver_path,
                result.stdout,
                result.stderr,
            )
        )
    version_text = "{}\n{}".format(result.stdout, result.stderr)
    expected_version = normalize_version(driver_version)
    if expected_version not in version_text:
        raise RuntimeError(
            "Installed xlsynth-driver at {} reported an unexpected version.\nexpected substring: {}\nstdout:\n{}\nstderr:\n{}".format(
                driver_path,
                expected_version,
                result.stdout,
                result.stderr,
            )
        )


def install_driver(repo_root, driver_version, libxls_path, dslx_stdlib_path, rustup_path = ""):
    host_platform = detect_host_platform()
    install_root = driver_install_root(repo_root, driver_version, host_platform)
    rustup_home = rustup_home_root(repo_root, host_platform)
    target_root = cargo_target_root(repo_root, host_platform)
    env = build_driver_install_environment(
        repo_root,
        libxls_path,
        dslx_stdlib_path,
        host_platform = host_platform,
    )
    for path in [install_root, rustup_home, target_root]:
        path.mkdir(parents = True, exist_ok = True)
    driver_path = install_root / "bin" / "xlsynth-driver"
    if driver_path.exists():
        try:
            validate_installed_driver(driver_path, env, driver_version)
            return driver_path
        except RuntimeError:
            ensure_clean_path(install_root)
            install_root.mkdir(parents = True, exist_ok = True)

    rustup = rustup_path or shutil.which("rustup")
    if rustup is None:
        raise RuntimeError(
            "rules_xlsynth download fallback requires rustup to install xlsynth-driver {}".format(
                driver_version
            )
        )
    ensure_rustup_nightly_toolchain(rustup, env)
    subprocess.run(
        build_driver_install_command(rustup, install_root, driver_version),
        check = True,
        env = env,
    )
    validate_installed_driver(driver_path, env, driver_version)
    return driver_path


def resolve_downloaded_artifacts(download_root):
    stdlib_root = download_root / "xls" / "dslx" / "stdlib"
    validate_stdlib_root(stdlib_root)
    for binary in TOOL_BINARIES:
        tool_path = download_root / binary
        if not tool_path.exists():
            raise RuntimeError("Expected tool binary at {}".format(tool_path))
    libxls_candidates = sorted(download_root.glob("libxls-*.so")) + sorted(download_root.glob("libxls-*.dylib"))
    if len(libxls_candidates) != 1:
        raise RuntimeError("Expected exactly one libxls artifact in {}, found {}".format(download_root, libxls_candidates))
    return {
        "tools_root": download_root,
        "dslx_stdlib_root": stdlib_root,
        "libxls": libxls_candidates[0],
        "runtime_files": load_runtime_manifest(download_root),
    }


def download_versioned_artifacts(repo_root, xls_version):
    script_path = Path(__file__).with_name("download_release.py")
    host_platform = detect_host_platform()
    download_root = downloaded_xls_root(repo_root, xls_version, host_platform)
    if download_root.exists():
        try:
            return resolve_downloaded_artifacts(download_root)
        except (RuntimeError, ValueError):
            ensure_clean_path(download_root)
    download_root.mkdir(parents = True, exist_ok = True)
    subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--output",
            str(download_root),
            "--platform",
            host_platform,
            "--version",
            version_tag(xls_version),
            "--dso",
        ],
        check = True,
    )
    return resolve_downloaded_artifacts(download_root)

def resolve_materialization_inputs(repo_root, plan):
    if plan["mode"] == "download":
        return download_versioned_artifacts(repo_root, plan["xls_version"])
    resolved = dict(plan)
    validate_stdlib_root(resolved["dslx_stdlib_root"])
    resolved["runtime_files"] = load_runtime_manifest(Path(resolved["libxls"]).parent)
    return resolved


def write_artifact_config(repo_root, libxls_dest):
    artifact_config_path = repo_root / "xlsynth_artifact_config.toml"
    artifact_config_path.write_text(
        "".join([
            "dso_path = \"{}\"\n".format(libxls_dest.name),
            "dslx_stdlib_path = \".\"\n",
        ]),
        encoding = "utf-8",
    )


def write_runtime_metadata(repo_root, libxls_dest, runtime_aliases, runtime_files):
    metadata_path = repo_root / "runtime_metadata.txt"
    metadata_path.write_text(
        "".join([
            "libxls_name={}\n".format(libxls_dest.name),
            "libxls_runtime_aliases={}\n".format(",".join(runtime_aliases)),
            "libxls_runtime_files={}\n".format(",".join(sorted(runtime_files))),
        ]),
        encoding = "utf-8",
    )


def write_toolchain_metadata(repo_root, driver_capabilities):
    metadata_path = repo_root / "toolchain_metadata.txt"
    metadata_path.write_text(
        "".join([
            "{}={}\n".format(
                capability_name,
                "true" if capability_enabled else "false",
            )
            for capability_name, capability_enabled in driver_capabilities.items()
        ]),
        encoding = "utf-8",
    )


def stage_runtime_payload(repo_root, resolved):
    link_tool_binaries(resolved["tools_root"], repo_root)
    link_stdlib_sources(resolved["dslx_stdlib_root"], repo_root)

    libxls_dest = repo_root / normalized_libxls_name(resolved["libxls"])
    copy_path(resolved["libxls"], libxls_dest)

    staged_runtime_files = []
    for runtime_file in resolved.get("runtime_files", []):
        runtime_dest = repo_root / runtime_file.name
        copy_path(runtime_file, runtime_dest)
        if runtime_dest.name not in staged_runtime_files:
            staged_runtime_files.append(runtime_dest.name)

    runtime_aliases = normalize_runtime_library_identity(libxls_dest)
    write_artifact_config(repo_root, libxls_dest)
    write_runtime_metadata(repo_root, libxls_dest, runtime_aliases, staged_runtime_files)
    return {
        "libxls_dest": libxls_dest,
        "runtime_aliases": runtime_aliases,
        "runtime_files": staged_runtime_files,
    }


def build_driver_probe_paths(repo_root):
    probe_root = repo_root / "_driver_probe"
    ensure_clean_path(probe_root)
    probe_root.mkdir(parents = True, exist_ok = True)
    return {
        "probe_root": probe_root,
        "stdlib_root": probe_root / "dslx_stdlib",
        "libxls": probe_root / normalized_libxls_name("libxls.so" if sys.platform == "linux" else "libxls.dylib"),
    }


def stage_driver_probe_inputs(repo_root, resolved):
    probe_paths = build_driver_probe_paths(repo_root)
    symlink_or_copy(resolved["dslx_stdlib_root"], probe_paths["stdlib_root"])
    copy_path(resolved["libxls"], probe_paths["libxls"])
    for runtime_file in resolved.get("runtime_files", []):
        probe_runtime_dest = probe_paths["probe_root"] / runtime_file.name
        copy_path(runtime_file, probe_runtime_dest)
    normalize_runtime_library_identity(probe_paths["libxls"])
    return probe_paths


def materialize_runtime_surface(repo_root, plan):
    resolved = resolve_materialization_inputs(repo_root, plan)
    stage_runtime_payload(repo_root, resolved)


def materialize_toolchain_surface(repo_root, plan):
    resolved = resolve_materialization_inputs(repo_root, plan)
    probe_paths = stage_driver_probe_inputs(repo_root, resolved)

    if plan["mode"] == "download":
        driver_path = install_driver(
            repo_root,
            plan["driver_version"],
            probe_paths["libxls"],
            probe_paths["stdlib_root"],
        )
    else:
        driver_path = resolved["driver"]

    driver_dest = repo_root / "xlsynth-driver"
    symlink_or_copy(driver_path, driver_dest)

    driver_capabilities = detect_driver_capabilities(
        driver_dest,
        probe_paths["libxls"],
        probe_paths["stdlib_root"],
    )
    write_toolchain_metadata(repo_root, driver_capabilities)


def materialize_driver_binary(
        repo_root,
        plan,
        driver_output,
        libxls_path,
        dslx_stdlib_path,
        rustup_path = ""):
    driver_env = build_driver_environment(libxls_path, dslx_stdlib_path)
    if plan["mode"] == "auto_driver_input":
        try:
            validate_installed_driver(
                plan["driver"],
                driver_env,
                plan["driver_version"],
            )
            driver_path = plan["driver"]
        except RuntimeError:
            fallback_plan = resolve_driver_plan(
                artifact_source = "auto",
                driver_version = plan["driver_version"],
                installed_driver_root_prefix = plan["installed_driver_root_prefix"],
            )
            materialize_driver_binary(
                repo_root,
                fallback_plan,
                driver_output,
                libxls_path,
                dslx_stdlib_path,
                rustup_path = rustup_path,
            )
            return
    elif plan["mode"] == "download":
        driver_path = install_driver(
            repo_root,
            plan["driver_version"],
            libxls_path,
            dslx_stdlib_path,
            rustup_path = rustup_path,
        )
    else:
        driver_path = plan["driver"]
        if plan["mode"] == "installed":
            validate_installed_driver(
                driver_path,
                driver_env,
                plan["driver_version"],
            )

    driver_output.parent.mkdir(parents = True, exist_ok = True)
    copy_path(driver_path, driver_output)
    driver_output.chmod(driver_output.stat().st_mode | 0o111)


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required = True)
    parser.add_argument("--artifact-source", required = True)
    parser.add_argument("--surface", required = True, choices = ["runtime", "toolchain"])
    parser.add_argument("--xls-version", default = "")
    parser.add_argument("--xlsynth-driver-version", default = "")
    parser.add_argument("--installed-tools-root-prefix", default = "")
    parser.add_argument("--installed-driver-root-prefix", default = "")
    parser.add_argument("--local-tools-path", default = "")
    parser.add_argument("--local-dslx-stdlib-path", default = "")
    parser.add_argument("--local-driver-path", default = "")
    parser.add_argument("--local-libxls-path", default = "")
    parser.add_argument("--driver-output", default = "")
    parser.add_argument("--driver-input", default = "")
    parser.add_argument("--driver-runtime-libxls", default = "")
    parser.add_argument("--driver-runtime-stdlib", default = "")
    parser.add_argument("--rustup-path", default = "")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    repo_root.mkdir(parents = True, exist_ok = True)
    if args.driver_output:
        if not args.driver_runtime_libxls or not args.driver_runtime_stdlib:
            raise ValueError("--driver-output requires --driver-runtime-libxls and --driver-runtime-stdlib")
        driver_plan = resolve_driver_plan(
            artifact_source = args.artifact_source,
            driver_version = args.xlsynth_driver_version,
            installed_driver_root_prefix = args.installed_driver_root_prefix,
            local_driver_path = args.local_driver_path,
            driver_input = args.driver_input,
        )
        materialize_driver_binary(
            repo_root,
            driver_plan,
            Path(args.driver_output).resolve(),
            Path(args.driver_runtime_libxls).resolve(),
            Path(args.driver_runtime_stdlib).resolve(),
            rustup_path = args.rustup_path,
        )
        return
    plan = resolve_artifact_plan(
        artifact_source = args.artifact_source,
        xls_version = args.xls_version,
        driver_version = args.xlsynth_driver_version,
        surface = args.surface,
        installed_tools_root_prefix = args.installed_tools_root_prefix,
        installed_driver_root_prefix = args.installed_driver_root_prefix,
        local_tools_path = args.local_tools_path,
        local_dslx_stdlib_path = args.local_dslx_stdlib_path,
        local_driver_path = args.local_driver_path,
        local_libxls_path = args.local_libxls_path,
    )
    if args.surface == "runtime":
        materialize_runtime_surface(repo_root, plan)
    else:
        materialize_toolchain_surface(repo_root, plan)


if __name__ == "__main__":
    main(sys.argv[1:])
