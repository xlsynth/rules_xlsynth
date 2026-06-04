# SPDX-License-Identifier: Apache-2.0

"""Materializes an XLS bundle repository for the rules_xlsynth module extension."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib import request as urlrequest

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

_XLSYNTH_REPO_URL = "https://github.com/xlsynth/xlsynth.git"
_XLSYNTH_CRATE_REPO_URL = "https://github.com/xlsynth/xlsynth-crate.git"
_XLSYNTH_CRATE_BUILD_RS_URL = (
    "https://raw.githubusercontent.com/xlsynth/xlsynth-crate/{}/xlsynth-sys/build.rs"
)
_GIT_REVISION_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_RELEASE_TAG_RE = re.compile(r"^v[0-9A-Za-z][0-9A-Za-z.+-]*$")
_XLS_RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9]+)?$")
_CRATE_IMPLIED_XLS_RELEASE_RE = re.compile(
    r'RELEASE_LIB_VERSION_TAG\s*:\s*&str\s*=\s*"([^"]+)"'
)
_DRIVER_GIT_PROVENANCE_FILENAME = "xlsynth-driver.provenance.json"
_PRIVATE_RUNTIME_FILENAMES = {"resolved_identity.json"}


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


def normalize_git_revision(revision):
    if not _GIT_REVISION_RE.fullmatch(revision):
        raise ValueError("Expected exact 40-character Git revision, got: {}".format(revision))
    return revision.lower()


def normalize_release_tag(version):
    tag = version_tag(version)
    if not _RELEASE_TAG_RE.fullmatch(tag):
        raise ValueError("Expected release tag, got: {}".format(version))
    return tag


def producer_pin(version, git_revision, label):
    if version and git_revision:
        raise ValueError("{} accepts either a release tag or a Git revision, not both".format(label))
    if version:
        return {
            "kind": "release_tag",
            "value": normalize_release_tag(version),
        }
    if git_revision:
        return {
            "kind": "git_revision",
            "value": normalize_git_revision(git_revision),
        }
    raise ValueError("{} requires either a release tag or a Git revision".format(label))


def list_remote_tag_revisions(repo_url):
    result = run_captured_text_command(
        ["git", "ls-remote", "--tags", repo_url],
        check = False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to list tags from {}\nstdout:\n{}\nstderr:\n{}".format(
                repo_url,
                result.stdout,
                result.stderr,
            )
        )
    direct_revisions = {}
    peeled_revisions = {}
    for line in result.stdout.splitlines():
        if not line:
            continue
        revision, ref = line.split("\t", 1)
        if not ref.startswith("refs/tags/"):
            continue
        tag = ref[len("refs/tags/"):]
        if tag.endswith("^{}"):
            peeled_revisions[tag[:-3]] = revision.lower()
        else:
            direct_revisions[tag] = revision.lower()
    direct_revisions.update(peeled_revisions)
    return direct_revisions


def read_url_text(url):
    with urlrequest.urlopen(url) as response:
        return response.read().decode("utf-8")


def resolve_release_tag_revision(repo_url, release_tag, list_remote_tags_fn = list_remote_tag_revisions):
    revisions = list_remote_tags_fn(repo_url)
    revision = revisions.get(release_tag)
    if revision is None:
        raise ValueError("{} does not publish release tag {}".format(repo_url, release_tag))
    return normalize_git_revision(revision)


def resolve_xls_pin(pin, list_remote_tags_fn = list_remote_tag_revisions):
    if pin["kind"] == "release_tag":
        release_tag = pin["value"]
        if not _XLS_RELEASE_TAG_RE.fullmatch(release_tag):
            raise ValueError("Expected XLS semantic release tag, got: {}".format(release_tag))
        return {
            "release_tag": release_tag,
            "revision": resolve_release_tag_revision(
                _XLSYNTH_REPO_URL,
                release_tag,
                list_remote_tags_fn = list_remote_tags_fn,
            ),
        }

    revision = normalize_git_revision(pin["value"])
    matching_tags = sorted(
        tag
        for tag, tag_revision in list_remote_tags_fn(_XLSYNTH_REPO_URL).items()
        if tag_revision == revision and _XLS_RELEASE_TAG_RE.fullmatch(tag)
    )
    if not matching_tags:
        raise ValueError(
            "XLS Git revision {} does not map to a published XLS release tag".format(revision)
        )
    if len(matching_tags) != 1:
        raise ValueError(
            "XLS Git revision {} maps to multiple published XLS release tags: {}".format(
                revision,
                ", ".join(matching_tags),
            )
        )
    return {
        "release_tag": matching_tags[0],
        "revision": revision,
    }


def crate_implied_xls_release_tag(crate_pin, read_text_fn = read_url_text):
    try:
        build_rs = read_text_fn(_XLSYNTH_CRATE_BUILD_RS_URL.format(crate_pin["value"]))
    except Exception as error:
        raise ValueError(
            "xlsynth-crate Git revision {} could not be resolved".format(crate_pin["value"])
        ) from error
    match = _CRATE_IMPLIED_XLS_RELEASE_RE.search(build_rs)
    if match is None:
        raise ValueError(
            "xlsynth-crate {} does not declare RELEASE_LIB_VERSION_TAG".format(
                crate_pin["value"],
            )
        )
    release_tag = match.group(1)
    if not _XLS_RELEASE_TAG_RE.fullmatch(release_tag):
        raise ValueError(
            "xlsynth-crate {} declares invalid XLS release tag {}".format(
                crate_pin["value"],
                release_tag,
            )
        )
    return release_tag


def resolve_archive_identity(
        xls_version,
        xls_git_revision,
        driver_version,
        driver_git_revision,
        allow_xls_pin_mismatch = False,
        list_remote_tags_fn = list_remote_tag_revisions,
        read_text_fn = read_url_text):
    xlsynth_crate_pin = producer_pin(driver_version, driver_git_revision, "xlsynth-crate pin")
    xls_pin = producer_pin(xls_version, xls_git_revision, "XLS pin")
    resolved_xls = resolve_xls_pin(xls_pin, list_remote_tags_fn = list_remote_tags_fn)
    if xlsynth_crate_pin["kind"] == "release_tag":
        resolved_crate_revision = resolve_release_tag_revision(
            _XLSYNTH_CRATE_REPO_URL,
            xlsynth_crate_pin["value"],
            list_remote_tags_fn = list_remote_tags_fn,
        )
    else:
        resolved_crate_revision = xlsynth_crate_pin["value"]
    implied_xls_release_tag = crate_implied_xls_release_tag(
        {
            "value": resolved_crate_revision,
        },
        read_text_fn = read_text_fn,
    )
    if implied_xls_release_tag != resolved_xls["release_tag"] and not allow_xls_pin_mismatch:
        raise ValueError(
            "xlsynth-crate {} implies XLS release {}, but explicit XLS pin resolves to {}; "
            "set allow_xls_pin_mismatch only for deliberate development overrides".format(
                xlsynth_crate_pin["value"],
                implied_xls_release_tag,
                resolved_xls["release_tag"],
            )
        )
    return {
        "schema_version": 1,
        "xlsynth_crate_pin": xlsynth_crate_pin,
        "xls_pin": xls_pin,
        "resolved_xlsynth_crate_revision": resolved_crate_revision,
        "crate_implied_xls_release_tag": implied_xls_release_tag,
        "resolved_xls_release_tag": resolved_xls["release_tag"],
        "resolved_xls_revision": resolved_xls["revision"],
    }


def write_resolved_identity(repo_root, identity):
    (repo_root / "resolved_identity.json").write_text(
        json.dumps(identity, indent = 2, sort_keys = True) + "\n",
        encoding = "utf-8",
    )


def validate_resolved_identity_inputs(
    artifact_source,
    local_xls_aot_runtime_source_path,
):
    if artifact_source != "download_only":
        raise ValueError(
            "trusted resolved identity requires artifact_source=download_only; "
            "{} may reuse consumer-owned artifacts".format(artifact_source)
        )
    elif local_xls_aot_runtime_source_path:
        raise ValueError(
            "trusted resolved identity cannot use local_xls_aot_runtime_source_path; "
            "the local source is not covered by the resolved XLS identity"
        )


def libxls_name_for_platform(sys_platform):
    if sys_platform == "darwin":
        return "libxls.dylib"
    elif sys_platform == "linux":
        return "libxls.so"
    else:
        raise RuntimeError("Unsupported host platform: {}".format(sys_platform))


def static_aot_runtime_name():
    return "libxls_aot_runtime.a"


def static_aot_runtime_link_config_name():
    return "libxls_aot_runtime_link.toml"


def static_aot_runtime_source_name():
    return "xls-aot-runtime-source.tar.gz"


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
        "xls_aot_runtime": tools_root / static_aot_runtime_name(),
        "xls_aot_runtime_link_config": tools_root / static_aot_runtime_link_config_name(),
        "xls_aot_runtime_source": tools_root / static_aot_runtime_source_name(),
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
        "xls_aot_runtime": tools_root / static_aot_runtime_name(),
        "xls_aot_runtime_link_config": tools_root / static_aot_runtime_link_config_name(),
        "xls_aot_runtime_source": tools_root / static_aot_runtime_source_name(),
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
    driver_git_revision = "",
    surface = "toolchain",
    installed_tools_root_prefix = "",
    installed_driver_root_prefix = "",
    local_tools_path = "",
    local_dslx_stdlib_path = "",
    local_driver_path = "",
    local_libxls_path = "",
    local_xls_aot_runtime_path = "",
    local_xls_aot_runtime_link_config_path = "",
    local_xls_aot_runtime_source_path = "",
    exists_fn = os.path.exists,
):
    if surface not in ("runtime", "toolchain"):
        raise ValueError("Unknown XLS bundle surface: {}".format(surface))
    include_driver = surface == "toolchain"
    if driver_version and driver_git_revision:
        raise ValueError("XLS bundle accepts either an xlsynth driver release tag or Git revision, not both")
    driver_identity = normalize_git_revision(driver_git_revision) if driver_git_revision else normalize_version(driver_version)

    if artifact_source == "local_paths":
        if xls_version or driver_identity:
            raise ValueError("local_paths does not accept XLS or xlsynth driver release or Git pins")
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
        if bool(local_xls_aot_runtime_path) != bool(local_xls_aot_runtime_link_config_path):
            raise ValueError(
                "local_paths requires local_xls_aot_runtime_path and "
                "local_xls_aot_runtime_link_config_path together"
            )
        plan = {
            "mode": "local_paths",
            "tools_root": Path(local_tools_path),
            "dslx_stdlib_root": Path(local_dslx_stdlib_path),
            "libxls": Path(local_libxls_path),
            "xls_aot_runtime": Path(local_xls_aot_runtime_path) if local_xls_aot_runtime_path else None,
            "xls_aot_runtime_link_config": (
                Path(local_xls_aot_runtime_link_config_path)
                if local_xls_aot_runtime_link_config_path
                else None
            ),
            "xls_aot_runtime_source": (
                Path(local_xls_aot_runtime_source_path)
                if local_xls_aot_runtime_source_path
                else None
            ),
        }
        if include_driver:
            plan["driver"] = Path(local_driver_path)
        return plan

    if artifact_source not in ("auto", "installed_only", "download_only"):
        raise ValueError("Unknown artifact_source: {}".format(artifact_source))
    if not xls_version:
        raise ValueError("{} requires xls_version".format(artifact_source))
    if include_driver and not driver_identity:
        raise ValueError("{} toolchain surface requires an xlsynth driver release or Git pin".format(artifact_source))
    if (
        local_tools_path
        or local_dslx_stdlib_path
        or local_driver_path
        or local_libxls_path
        or local_xls_aot_runtime_path
        or local_xls_aot_runtime_link_config_path
    ):
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
            driver_version = driver_identity,
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
        if local_xls_aot_runtime_source_path:
            plan["xls_aot_runtime_source"] = Path(local_xls_aot_runtime_source_path)
        if include_driver:
            plan["driver_version"] = normalize_version(driver_version)
            if driver_git_revision:
                plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
        return plan

    installed_paths_present = all(
        exists_fn(str(path))
        for name, path in installed_paths.items()
        if name not in (
            "xls_aot_runtime",
            "xls_aot_runtime_link_config",
            "xls_aot_runtime_source",
        )
    )
    installed_aot_runtime_present = exists_fn(str(installed_paths["xls_aot_runtime"]))
    installed_aot_runtime_link_config_present = exists_fn(
        str(installed_paths["xls_aot_runtime_link_config"])
    )
    installed_aot_runtime_source_present = exists_fn(
        str(installed_paths["xls_aot_runtime_source"])
    )
    if installed_aot_runtime_present != installed_aot_runtime_link_config_present:
        raise ValueError(
            "installed paths require libxls_aot_runtime.a and "
            "libxls_aot_runtime_link.toml together"
        )
    if artifact_source == "auto" and installed_paths_present:
        plan = {
            "mode": "installed",
            "tools_root": installed_paths["tools_root"],
            "dslx_stdlib_root": installed_paths["dslx_stdlib_root"],
            "libxls": installed_paths["libxls"],
            "xls_aot_runtime": (
                installed_paths["xls_aot_runtime"]
                if installed_aot_runtime_present
                else None
            ),
            "xls_aot_runtime_link_config": (
                installed_paths["xls_aot_runtime_link_config"]
                if installed_aot_runtime_link_config_present
                else None
            ),
            "xls_aot_runtime_source": (
                installed_paths["xls_aot_runtime_source"]
                if installed_aot_runtime_source_present
                else None
            ),
        }
        if include_driver:
            plan["driver"] = installed_paths["driver"]
            plan["driver_version"] = normalize_version(driver_version)
            if driver_git_revision:
                plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
        if local_xls_aot_runtime_source_path:
            plan["xls_aot_runtime_source"] = Path(local_xls_aot_runtime_source_path)
        return plan
    if artifact_source == "installed_only":
        if not installed_paths_present:
            message = "installed_only requires exact-version installed paths for XLS {}".format(
                normalize_version(xls_version),
            )
            if include_driver:
                message = "{} and driver {}".format(message, driver_identity)
            raise ValueError(message)
        plan = {
            "mode": "installed",
            "tools_root": installed_paths["tools_root"],
            "dslx_stdlib_root": installed_paths["dslx_stdlib_root"],
            "libxls": installed_paths["libxls"],
            "xls_aot_runtime": (
                installed_paths["xls_aot_runtime"]
                if installed_aot_runtime_present
                else None
            ),
            "xls_aot_runtime_link_config": (
                installed_paths["xls_aot_runtime_link_config"]
                if installed_aot_runtime_link_config_present
                else None
            ),
            "xls_aot_runtime_source": (
                installed_paths["xls_aot_runtime_source"]
                if installed_aot_runtime_source_present
                else None
            ),
        }
        if include_driver:
            plan["driver"] = installed_paths["driver"]
            plan["driver_version"] = normalize_version(driver_version)
            if driver_git_revision:
                plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
        if local_xls_aot_runtime_source_path:
            plan["xls_aot_runtime_source"] = Path(local_xls_aot_runtime_source_path)
        return plan
    plan = {
        "mode": "download",
        "xls_version": normalize_version(xls_version),
    }
    if local_xls_aot_runtime_source_path:
        plan["xls_aot_runtime_source"] = Path(local_xls_aot_runtime_source_path)
    if include_driver:
        plan["driver_version"] = normalize_version(driver_version)
        if driver_git_revision:
            plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
    return plan


def resolve_driver_plan(
    artifact_source,
    driver_version,
    driver_git_revision = "",
    installed_driver_root_prefix = "",
    local_driver_path = "",
    driver_input = "",
    exists_fn = os.path.exists,
):
    if driver_version and driver_git_revision:
        raise ValueError("xlsynth-driver materialization accepts either a release tag or a Git revision, not both")
    driver_identity = normalize_git_revision(driver_git_revision) if driver_git_revision else normalize_version(driver_version)
    if artifact_source == "local_paths":
        if driver_identity:
            raise ValueError("local_paths does not accept xlsynth driver release or Git pins")
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
            if not driver_identity:
                raise ValueError("auto declared driver input requires an xlsynth driver release or Git pin")
            plan = {
                "mode": "auto_driver_input",
                "driver": Path(driver_input),
                "driver_version": normalize_version(driver_version),
                "installed_driver_root_prefix": installed_driver_root_prefix,
            }
            if driver_git_revision:
                plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
            return plan
        if artifact_source in ("auto", "installed_only"):
            if not driver_identity:
                raise ValueError("{} declared driver input requires an xlsynth driver release or Git pin".format(artifact_source))
            plan = {
                "mode": "installed",
                "driver": Path(driver_input),
                "driver_version": normalize_version(driver_version),
            }
            if driver_git_revision:
                plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
            return plan
        if artifact_source == "download_only":
            raise ValueError("download_only driver materialization does not accept driver_input")
        raise ValueError("Unknown artifact_source: {}".format(artifact_source))

    if artifact_source not in ("auto", "installed_only", "download_only"):
        raise ValueError("Unknown artifact_source: {}".format(artifact_source))
    if not driver_identity:
        raise ValueError("{} driver materialization requires an xlsynth driver release or Git pin".format(artifact_source))
    if artifact_source == "download_only":
        if installed_driver_root_prefix:
            raise ValueError("download_only driver materialization does not accept installed_driver_root_prefix")
        plan = {
            "mode": "download",
            "driver_version": normalize_version(driver_version),
        }
        if driver_git_revision:
            plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
        return plan

    if not installed_driver_root_prefix:
        raise ValueError("{} driver materialization requires installed_driver_root_prefix".format(artifact_source))

    installed_driver = Path(installed_driver_root_prefix) / driver_identity / "bin" / "xlsynth-driver"
    if exists_fn(str(installed_driver)):
        plan = {
            "mode": "auto_installed" if artifact_source == "auto" else "installed",
            "driver": installed_driver,
            "driver_version": normalize_version(driver_version),
        }
        if driver_git_revision:
            plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
        return plan
    if artifact_source == "installed_only":
        raise ValueError(
            "installed_only driver materialization requires installed path for driver {}".format(
                driver_identity,
            )
        )
    plan = {
        "mode": "download",
        "driver_version": normalize_version(driver_version),
    }
    if driver_git_revision:
        plan["driver_git_revision"] = normalize_git_revision(driver_git_revision)
    return plan


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


def driver_install_root(repo_root, driver_identity, host_platform):
    return repo_root / "_cargo_driver" / host_platform / driver_identity


def rustup_home_root(repo_root, host_platform):
    return repo_root / "_rustup_home" / host_platform


def cargo_home_root(repo_root, host_platform):
    return repo_root / "_cargo_home" / host_platform


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


def build_driver_git_install_command(rustup_path, install_root, driver_git_revision):
    return [
        rustup_path,
        "run",
        "nightly",
        "cargo",
        "install",
        "--locked",
        "--root",
        str(install_root),
        "--git",
        _XLSYNTH_CRATE_REPO_URL,
        "--rev",
        normalize_git_revision(driver_git_revision),
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
    env["CARGO_HOME"] = str(cargo_home_root(repo_root, resolved_host_platform))
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


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def driver_git_provenance_path(driver_path):
    return Path(driver_path).parent / _DRIVER_GIT_PROVENANCE_FILENAME


def write_driver_git_provenance(driver_path, driver_git_revision):
    revision = normalize_git_revision(driver_git_revision)
    provenance = {
        "schema_version": 1,
        "source_repository": _XLSYNTH_CRATE_REPO_URL,
        "git_revision": revision,
        "driver_sha256": sha256_file(driver_path),
    }
    driver_git_provenance_path(driver_path).write_text(
        json.dumps(provenance, indent = 2, sort_keys = True) + "\n",
        encoding = "utf-8",
    )


def validate_driver_git_provenance(driver_path, driver_git_revision):
    revision = normalize_git_revision(driver_git_revision)
    provenance_path = driver_git_provenance_path(driver_path)
    try:
        provenance = json.loads(provenance_path.read_text(encoding = "utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Installed Git-pinned xlsynth-driver at {} requires valid provenance at {}".format(
                driver_path,
                provenance_path,
            )
        ) from error
    expected = {
        "schema_version": 1,
        "source_repository": _XLSYNTH_CRATE_REPO_URL,
        "git_revision": revision,
        "driver_sha256": sha256_file(driver_path),
    }
    if provenance != expected:
        raise RuntimeError(
            "Installed Git-pinned xlsynth-driver provenance at {} does not match "
            "the requested revision and driver bytes".format(provenance_path)
        )


def validate_installed_driver(
        driver_path,
        env,
        driver_version = "",
        driver_git_revision = ""):
    if driver_version and driver_git_revision:
        raise ValueError("installed driver validation accepts either a release tag or Git revision, not both")
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
    if expected_version and expected_version not in version_text:
        raise RuntimeError(
            "Installed xlsynth-driver at {} reported an unexpected version.\nexpected substring: {}\nstdout:\n{}\nstderr:\n{}".format(
                driver_path,
                expected_version,
                result.stdout,
                result.stderr,
            )
        )
    elif driver_git_revision:
        validate_driver_git_provenance(driver_path, driver_git_revision)


def install_driver(
        repo_root,
        driver_version,
        libxls_path,
        dslx_stdlib_path,
        rustup_path = "",
        driver_git_revision = ""):
    if driver_version and driver_git_revision:
        raise ValueError("xlsynth-driver install accepts either a release tag or a Git revision, not both")
    driver_identity = (
        normalize_git_revision(driver_git_revision)
        if driver_git_revision
        else normalize_version(driver_version)
    )
    if not driver_identity:
        raise ValueError("xlsynth-driver install requires a release tag or Git revision")
    host_platform = detect_host_platform()
    install_root = driver_install_root(repo_root, driver_identity, host_platform)
    rustup_home = rustup_home_root(repo_root, host_platform)
    cargo_home = cargo_home_root(repo_root, host_platform)
    target_root = cargo_target_root(repo_root, host_platform)
    env = build_driver_install_environment(
        repo_root,
        libxls_path,
        dslx_stdlib_path,
        host_platform = host_platform,
    )
    for path in [install_root, rustup_home, cargo_home, target_root]:
        path.mkdir(parents = True, exist_ok = True)
    driver_path = install_root / "bin" / "xlsynth-driver"
    if driver_path.exists():
        try:
            validate_installed_driver(
                driver_path,
                env,
                driver_version,
                driver_git_revision,
            )
            return driver_path
        except RuntimeError:
            ensure_clean_path(install_root)
            install_root.mkdir(parents = True, exist_ok = True)

    rustup = rustup_path or shutil.which("rustup")
    if rustup is None:
        raise RuntimeError(
            "rules_xlsynth download fallback requires rustup to install xlsynth-driver {}".format(
                driver_identity
            )
        )
    ensure_rustup_nightly_toolchain(rustup, env)
    if driver_git_revision:
        install_command = build_driver_git_install_command(
            rustup,
            install_root,
            driver_git_revision,
        )
    else:
        install_command = build_driver_install_command(rustup, install_root, driver_version)
    subprocess.run(
        install_command,
        check = True,
        env = env,
    )
    if driver_git_revision:
        write_driver_git_provenance(driver_path, driver_git_revision)
    validate_installed_driver(
        driver_path,
        env,
        driver_version,
        driver_git_revision,
    )
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
    static_aot_runtime_candidates = sorted(download_root.glob("libxls_aot_runtime-*.a"))
    if len(static_aot_runtime_candidates) > 1:
        raise RuntimeError(
            "Expected at most one libxls_aot_runtime artifact in {}, found {}".format(
                download_root,
                static_aot_runtime_candidates,
            )
        )
    static_aot_runtime_link_config_candidates = sorted(
        download_root.glob("libxls_aot_runtime_link-*.toml")
    )
    if len(static_aot_runtime_link_config_candidates) > 1:
        raise RuntimeError(
            "Expected at most one libxls_aot_runtime link config artifact in {}, found {}".format(
                download_root,
                static_aot_runtime_link_config_candidates,
            )
        )
    if bool(static_aot_runtime_candidates) != bool(static_aot_runtime_link_config_candidates):
        raise RuntimeError(
            "Expected libxls_aot_runtime archive and link config together in {}".format(
                download_root
            )
        )
    static_aot_runtime_source = download_root / static_aot_runtime_source_name()
    return {
        "tools_root": download_root,
        "dslx_stdlib_root": stdlib_root,
        "libxls": libxls_candidates[0],
        "xls_aot_runtime": static_aot_runtime_candidates[0] if static_aot_runtime_candidates else None,
        "xls_aot_runtime_link_config": (
            static_aot_runtime_link_config_candidates[0]
            if static_aot_runtime_link_config_candidates
            else None
        ),
        "xls_aot_runtime_source": (
            static_aot_runtime_source
            if static_aot_runtime_source.exists()
            else None
        ),
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
        resolved = download_versioned_artifacts(repo_root, plan["xls_version"])
        if plan.get("xls_aot_runtime_source") is not None:
            resolved["xls_aot_runtime_source"] = plan["xls_aot_runtime_source"]
        return resolved
    resolved = dict(plan)
    validate_stdlib_root(resolved["dslx_stdlib_root"])
    resolved["runtime_files"] = load_runtime_manifest(Path(resolved["libxls"]).parent)
    return resolved


def write_artifact_config(
        repo_root,
        libxls_dest,
        xls_aot_runtime_dest,
        xls_aot_runtime_link_config_dest,
):
    artifact_config_path = repo_root / "xlsynth_artifact_config.toml"
    config_lines = [
        "dso_path = \"{}\"\n".format(libxls_dest.name),
        "dslx_stdlib_path = \".\"\n",
    ]
    if xls_aot_runtime_dest is not None:
        config_lines.append("aot_runtime_path = \"{}\"\n".format(xls_aot_runtime_dest.name))
        config_lines.append(
            "aot_runtime_link_config_path = \"{}\"\n".format(
                xls_aot_runtime_link_config_dest.name
            )
        )
    artifact_config_path.write_text("".join(config_lines), encoding = "utf-8")


def write_runtime_metadata(
        repo_root,
        libxls_dest,
        xls_aot_runtime_dest,
        xls_aot_runtime_link_config_dest,
        xls_aot_runtime_source_repo,
        runtime_aliases,
        runtime_files,
):
    metadata_path = repo_root / "runtime_metadata.txt"
    metadata_path.write_text(
        "".join([
            "libxls_name={}\n".format(libxls_dest.name),
            "xls_aot_runtime_name={}\n".format(
                xls_aot_runtime_dest.name if xls_aot_runtime_dest is not None else "",
            ),
            "xls_aot_runtime_link_config_name={}\n".format(
                xls_aot_runtime_link_config_dest.name
                if xls_aot_runtime_link_config_dest is not None
                else "",
            ),
            "xls_aot_runtime_source_repo={}\n".format(
                xls_aot_runtime_source_repo.name
                if xls_aot_runtime_source_repo is not None
                else "",
            ),
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
    xls_aot_runtime_dest = None
    xls_aot_runtime_link_config_dest = None
    if resolved.get("xls_aot_runtime") is not None:
        xls_aot_runtime_dest = repo_root / static_aot_runtime_name()
        copy_path(resolved["xls_aot_runtime"], xls_aot_runtime_dest)
        xls_aot_runtime_link_config_dest = repo_root / static_aot_runtime_link_config_name()
        copy_path(
            resolved["xls_aot_runtime_link_config"],
            xls_aot_runtime_link_config_dest,
        )
    xls_aot_runtime_source_repo = None
    if resolved.get("xls_aot_runtime_source") is not None:
        xls_aot_runtime_source_repo = repo_root / "xls_aot_runtime_source"
        ensure_clean_path(xls_aot_runtime_source_repo)
        shutil.unpack_archive(
            str(resolved["xls_aot_runtime_source"]),
            str(xls_aot_runtime_source_repo),
        )
        if not (xls_aot_runtime_source_repo / "BUILD.bazel").is_file():
            raise ValueError(
                "Standalone AOT runtime source archive must unpack BUILD.bazel at {}".format(
                    xls_aot_runtime_source_repo,
                )
            )

    staged_runtime_files = []
    for runtime_file in resolved.get("runtime_files", []):
        runtime_dest = repo_root / runtime_file.name
        copy_path(runtime_file, runtime_dest)
        if runtime_dest.name not in staged_runtime_files:
            staged_runtime_files.append(runtime_dest.name)

    runtime_aliases = normalize_runtime_library_identity(libxls_dest)
    write_artifact_config(
        repo_root,
        libxls_dest,
        xls_aot_runtime_dest,
        xls_aot_runtime_link_config_dest,
    )
    write_runtime_metadata(
        repo_root,
        libxls_dest,
        xls_aot_runtime_dest,
        xls_aot_runtime_link_config_dest,
        xls_aot_runtime_source_repo,
        runtime_aliases,
        staged_runtime_files,
    )
    return {
        "libxls_dest": libxls_dest,
        "xls_aot_runtime_dest": xls_aot_runtime_dest,
        "xls_aot_runtime_link_config_dest": xls_aot_runtime_link_config_dest,
        "xls_aot_runtime_source_repo": xls_aot_runtime_source_repo,
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


def materialize_runtime_surface(repo_root, plan, resolved_identity = None):
    resolved = resolve_materialization_inputs(repo_root, plan)
    colliding_runtime_files = sorted(
        runtime_file.name
        for runtime_file in resolved.get("runtime_files", [])
        if runtime_file.name in _PRIVATE_RUNTIME_FILENAMES
    )
    if colliding_runtime_files:
        raise ValueError(
            "runtime payload uses reserved private filenames: {}".format(
                ", ".join(colliding_runtime_files),
            )
        )
    stage_runtime_payload(repo_root, resolved)
    ensure_clean_path(repo_root / "resolved_identity.json")
    if resolved_identity is not None:
        write_resolved_identity(repo_root, resolved_identity)


def materialize_toolchain_surface(repo_root, plan):
    resolved = resolve_materialization_inputs(repo_root, plan)
    probe_paths = stage_driver_probe_inputs(repo_root, resolved)

    if plan["mode"] == "download":
        driver_path = install_driver(
            repo_root,
            plan["driver_version"],
            probe_paths["libxls"],
            probe_paths["stdlib_root"],
            driver_git_revision = plan.get("driver_git_revision", ""),
        )
    else:
        driver_path = resolved["driver"]
        if (
            plan["mode"] == "installed"
            and (plan.get("driver_version") or plan.get("driver_git_revision"))
        ):
            validate_installed_driver(
                driver_path,
                build_driver_environment(
                    probe_paths["libxls"],
                    probe_paths["stdlib_root"],
                ),
                plan.get("driver_version", ""),
                plan.get("driver_git_revision", ""),
            )

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
    if plan["mode"] in ("auto_driver_input", "auto_installed"):
        try:
            validate_installed_driver(
                plan["driver"],
                driver_env,
                plan["driver_version"],
                plan.get("driver_git_revision", ""),
            )
            driver_path = plan["driver"]
        except RuntimeError:
            fallback_plan = {
                "mode": "download",
                "driver_version": plan["driver_version"],
            }
            if plan.get("driver_git_revision"):
                fallback_plan["driver_git_revision"] = plan["driver_git_revision"]
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
            driver_git_revision = plan.get("driver_git_revision", ""),
        )
    else:
        driver_path = plan["driver"]
        if plan["mode"] == "installed":
            validate_installed_driver(
                driver_path,
                driver_env,
                plan["driver_version"],
                plan.get("driver_git_revision", ""),
            )

    driver_output.parent.mkdir(parents = True, exist_ok = True)
    copy_path(driver_path, driver_output)
    driver_output.chmod(driver_output.stat().st_mode | 0o111)


def validate_and_copy_driver_resolved_identity(
        identity_input,
        identity_output,
        plan,
        allow_xls_pin_mismatch = False):
    identity = json.loads(Path(identity_input).read_text(encoding = "utf-8"))
    required_fields = {
        "schema_version",
        "xlsynth_crate_pin",
        "xls_pin",
        "resolved_xlsynth_crate_revision",
        "crate_implied_xls_release_tag",
        "resolved_xls_release_tag",
        "resolved_xls_revision",
    }
    if set(identity) != required_fields:
        raise ValueError(
            "resolved identity fields {} do not match required schema fields {}".format(
                sorted(identity),
                sorted(required_fields),
            )
        )
    if identity["schema_version"] != 1:
        raise ValueError(
            "resolved identity schema_version {} is unsupported".format(
                identity["schema_version"],
            )
        )
    for field in ["xlsynth_crate_pin", "xls_pin"]:
        pin = identity[field]
        if (
            not isinstance(pin, dict)
            or set(pin) != {"kind", "value"}
            or pin.get("kind") not in ("release_tag", "git_revision")
            or not isinstance(pin.get("value"), str)
            or not pin["value"]
        ):
            raise ValueError("resolved identity {} is malformed: {}".format(field, pin))
        if pin["kind"] == "release_tag":
            if pin["value"] != normalize_release_tag(pin["value"]):
                raise ValueError(
                    "resolved identity {} release tag is malformed: {}".format(field, pin["value"])
                )
            if field == "xls_pin" and not _XLS_RELEASE_TAG_RE.fullmatch(pin["value"]):
                raise ValueError(
                    "resolved identity {} is not an XLS release tag: {}".format(
                        field,
                        pin["value"],
                    )
                )
        elif pin["value"] != normalize_git_revision(pin["value"]):
            raise ValueError(
                "resolved identity {} Git revision must be a lowercase exact SHA".format(field)
            )
    for field in ["resolved_xlsynth_crate_revision", "resolved_xls_revision"]:
        revision = identity[field]
        if (
            not isinstance(revision, str)
            or len(revision) != 40
            or any(character not in "0123456789abcdef" for character in revision)
        ):
            raise ValueError(
                "resolved identity {} is not a lowercase 40-character Git SHA".format(field)
            )
    for field in ["crate_implied_xls_release_tag", "resolved_xls_release_tag"]:
        release_tag = identity[field]
        if not isinstance(release_tag, str) or not _XLS_RELEASE_TAG_RE.fullmatch(release_tag):
            raise ValueError("resolved identity {} is not an XLS release tag".format(field))
    expected_pin = producer_pin(
        plan.get("driver_version", ""),
        plan.get("driver_git_revision", ""),
        "xlsynth-driver materialization pin",
    )
    if identity.get("xlsynth_crate_pin") != expected_pin:
        raise ValueError(
            "resolved identity xlsynth-crate pin {} does not match selected driver pin {}".format(
                identity.get("xlsynth_crate_pin"),
                expected_pin,
            )
        )
    # Release tag-to-SHA mappings were resolved before the private runtime
    # repository was generated; this action verifies all local relationships.
    crate_pin = identity["xlsynth_crate_pin"]
    if (
        crate_pin["kind"] == "git_revision"
        and crate_pin["value"] != identity["resolved_xlsynth_crate_revision"]
    ):
        raise ValueError(
            "resolved identity xlsynth-crate Git pin does not match "
            "resolved_xlsynth_crate_revision"
        )
    xls_pin = identity["xls_pin"]
    if xls_pin["kind"] == "git_revision":
        if xls_pin["value"] != identity["resolved_xls_revision"]:
            raise ValueError(
                "resolved identity XLS Git pin does not match resolved_xls_revision"
            )
    elif xls_pin["value"] != identity["resolved_xls_release_tag"]:
        raise ValueError(
            "resolved identity XLS release pin does not match resolved_xls_release_tag"
        )
    if (
        not allow_xls_pin_mismatch
        and identity["crate_implied_xls_release_tag"] != identity["resolved_xls_release_tag"]
    ):
        raise ValueError(
            "resolved identity crate-implied XLS release does not match "
            "the resolved XLS release without an explicit development override"
        )
    identity_output = Path(identity_output)
    identity_output.parent.mkdir(parents = True, exist_ok = True)
    copy_path(Path(identity_input), identity_output)


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required = True)
    parser.add_argument("--artifact-source", required = True)
    parser.add_argument("--surface", required = True, choices = ["runtime", "toolchain"])
    parser.add_argument("--xls-version", default = "")
    parser.add_argument("--xls-git-revision", default = "")
    parser.add_argument("--xlsynth-driver-version", default = "")
    parser.add_argument("--xlsynth-driver-git-revision", default = "")
    parser.add_argument("--emit-resolved-identity", action = "store_true")
    parser.add_argument("--allow-xls-pin-mismatch", action = "store_true")
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
    parser.add_argument("--driver-resolved-identity-input", default = "")
    parser.add_argument("--driver-resolved-identity-output", default = "")
    parser.add_argument("--rustup-path", default = "")
    parser.add_argument("--local-xls-aot-runtime-path", default = "")
    parser.add_argument("--local-xls-aot-runtime-link-config-path", default = "")
    parser.add_argument("--local-xls-aot-runtime-source-path", default = "")
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
            driver_git_revision = args.xlsynth_driver_git_revision,
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
        if bool(args.driver_resolved_identity_input) != bool(args.driver_resolved_identity_output):
            raise ValueError(
                "--driver-resolved-identity-input and --driver-resolved-identity-output are required together"
            )
        if args.driver_resolved_identity_input:
            validate_and_copy_driver_resolved_identity(
                args.driver_resolved_identity_input,
                args.driver_resolved_identity_output,
                driver_plan,
                allow_xls_pin_mismatch = args.allow_xls_pin_mismatch,
            )
        return
    resolved_identity = None
    materialized_xls_version = args.xls_version
    if args.xls_version and args.xls_git_revision:
        raise ValueError("XLS materialization accepts either a release tag or Git revision, not both")
    if args.emit_resolved_identity:
        validate_resolved_identity_inputs(
            args.artifact_source,
            args.local_xls_aot_runtime_source_path,
        )
        resolved_identity = resolve_archive_identity(
            xls_version = args.xls_version,
            xls_git_revision = args.xls_git_revision,
            driver_version = args.xlsynth_driver_version,
            driver_git_revision = args.xlsynth_driver_git_revision,
            allow_xls_pin_mismatch = args.allow_xls_pin_mismatch,
        )
        materialized_xls_version = resolved_identity["resolved_xls_release_tag"]
    elif args.xls_git_revision:
        materialized_xls_version = resolve_xls_pin(
            producer_pin("", args.xls_git_revision, "XLS pin"),
        )["release_tag"]
    plan = resolve_artifact_plan(
        artifact_source = args.artifact_source,
        xls_version = materialized_xls_version,
        driver_version = args.xlsynth_driver_version,
        driver_git_revision = args.xlsynth_driver_git_revision,
        surface = args.surface,
        installed_tools_root_prefix = args.installed_tools_root_prefix,
        installed_driver_root_prefix = args.installed_driver_root_prefix,
        local_tools_path = args.local_tools_path,
        local_dslx_stdlib_path = args.local_dslx_stdlib_path,
        local_driver_path = args.local_driver_path,
        local_libxls_path = args.local_libxls_path,
        local_xls_aot_runtime_path = args.local_xls_aot_runtime_path,
        local_xls_aot_runtime_link_config_path = args.local_xls_aot_runtime_link_config_path,
        local_xls_aot_runtime_source_path = args.local_xls_aot_runtime_source_path,
    )
    if args.xlsynth_driver_git_revision:
        if args.artifact_source == "local_paths":
            raise ValueError("local_paths does not accept xlsynth driver Git pins")
        plan["driver_git_revision"] = normalize_git_revision(args.xlsynth_driver_git_revision)
    if args.surface == "runtime":
        materialize_runtime_surface(repo_root, plan, resolved_identity = resolved_identity)
    else:
        materialize_toolchain_surface(repo_root, plan)


if __name__ == "__main__":
    main(sys.argv[1:])
