_TOOL_BINARIES = [
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
_DRIVER_GIT_PROVENANCE_FILENAME = "xlsynth-driver.provenance.json"

def _metadata_dict(repo_ctx, metadata_filename):
    metadata = {}
    metadata_path = repo_ctx.path(metadata_filename)
    if not metadata_path.exists:
        fail("Missing bundle metadata at {}".format(metadata_path))
    for line in repo_ctx.read(metadata_filename).splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        metadata[key] = value
    return metadata

def _runtime_repo_name(name):
    return name + "_runtime"

def _toolchain_repo_name(name):
    return name + "_toolchain"

def _driver_repo_name(name):
    return name + "_driver"

def _installed_driver_path(driver_version, installed_driver_root_prefix):
    return "{}/{}/bin/xlsynth-driver".format(
        installed_driver_root_prefix.rstrip("/"),
        _normalize_version_text(driver_version),
    )

def _quoted(value):
    return "\"{}\"".format(value.replace("\\", "\\\\").replace("\"", "\\\""))

def _normalize_version_text(version):
    if version.startswith("v"):
        return version[1:]
    return version

def _version_components(version):
    core = _normalize_version_text(version).split("-", 1)[0].split("+", 1)[0]
    components = []
    for raw_part in core.split("."):
        components.append(int(raw_part or "0"))
    for _unused in range(3):
        if len(components) < 3:
            components.append(0)
    return [components[0], components[1], components[2]]

def _version_at_least(version, minimum):
    version_components = _version_components(version)
    minimum_components = _version_components(minimum)
    for index in range(3):
        if version_components[index] > minimum_components[index]:
            return True
        if version_components[index] < minimum_components[index]:
            return False
    return True

def _driver_supports_sv_enum_case_naming_policy(driver_version):
    if not driver_version:
        return False
    return _version_at_least(driver_version, "0.33.0")

def _driver_supports_sv_struct_field_ordering(driver_version):
    if not driver_version:
        return False
    return _version_at_least(driver_version, "0.36.0")

def _toolchain_driver_supports_sv_enum_case_naming_policy(
        artifact_source,
        local_driver_path,
        xlsynth_driver_git_revision,
        xlsynth_driver_version):
    if artifact_source == "local_paths" and local_driver_path:
        supports = True
    elif xlsynth_driver_git_revision:
        supports = False
    else:
        supports = _driver_supports_sv_enum_case_naming_policy(xlsynth_driver_version)
    return supports

def _toolchain_driver_supports_sv_struct_field_ordering(
        artifact_source,
        local_driver_path,
        xlsynth_driver_git_revision,
        xlsynth_driver_version):
    if artifact_source == "local_paths" and local_driver_path:
        supports = True
    elif xlsynth_driver_git_revision:
        supports = False
    else:
        supports = _driver_supports_sv_struct_field_ordering(xlsynth_driver_version)
    return supports

def _runtime_build_file(
        libxls_name,
        xls_aot_runtime_name,
        xls_aot_runtime_link_config_name,
        xls_aot_runtime_source_repo,
        runtime_files,
        runtime_aliases,
        resolved_identity,
        toolchain_repo_name):
    tool_list = ",\n        ".join(['"{}"'.format(name) for name in _TOOL_BINARIES])
    exported_names = _TOOL_BINARIES + [libxls_name] + runtime_files + runtime_aliases
    if xls_aot_runtime_name:
        exported_names.append(xls_aot_runtime_name)
        exported_names.append(xls_aot_runtime_link_config_name)
    exported_files = ",\n    ".join(['"{}"'.format(name) for name in exported_names])
    runtime_file_srcs = ",\n        ".join(['"{}"'.format(name) for name in runtime_files])
    runtime_alias_srcs = ",\n        ".join(['"{}"'.format(name) for name in runtime_aliases])
    lib_target = libxls_name
    aot_runtime_rule = """
filegroup(
    name = "xls_aot_runtime_file",
    srcs = ["{xls_aot_runtime_name}"],
    visibility = ["//visibility:public"],
)
filegroup(
    name = "xls_aot_runtime_link_config_file",
    srcs = ["{xls_aot_runtime_link_config_name}"],
    visibility = ["//visibility:public"],
)
cc_import(
    name = "xls_aot_runtime",
    static_library = ":xls_aot_runtime_file",
    visibility = ["//visibility:public"],
)
""".format(
        xls_aot_runtime_name = xls_aot_runtime_name,
        xls_aot_runtime_link_config_name = xls_aot_runtime_link_config_name,
    ) if xls_aot_runtime_name else ""
    aot_runtime_source_rule = """
alias(
    name = "xls_aot_runtime_source_dep",
    actual = "//{xls_aot_runtime_source_repo}:standalone_aot_runtime",
    visibility = ["//visibility:public"],
)
""".format(
        xls_aot_runtime_source_repo = xls_aot_runtime_source_repo,
    ) if xls_aot_runtime_source_repo else ""
    resolved_identity_rule = """
filegroup(
    name = "resolved_identity_for_toolchain",
    srcs = ["resolved_identity.json"],
    visibility = ["@{toolchain_repo_name}//:__pkg__"],
)
""".format(
        toolchain_repo_name = toolchain_repo_name,
    ) if resolved_identity else ""
    lib_file_rule = """
filegroup(
    name = "libxls_file",
    srcs = ["{lib_target}"],
    visibility = ["//visibility:public"],
)
filegroup(
    name = "libxls_runtime_files",
    srcs = [":libxls_file"{runtime_file_srcs}{runtime_alias_srcs}],
    visibility = ["//visibility:public"],
)
cc_import(
    name = "libxls",
    shared_library = ":libxls_file",
    visibility = ["//visibility:public"],
)
xls_shared_library_link(
    name = "libxls_link",
    runtime_files = ":libxls_runtime_files",
    shared_library = ":libxls_file",
    visibility = ["//visibility:public"],
)
""".format(
        lib_target = lib_target,
        runtime_file_srcs = "" if not runtime_files else ",\n        {}".format(runtime_file_srcs),
        runtime_alias_srcs = "" if not runtime_aliases else ",\n        {}".format(runtime_alias_srcs),
    )
    return """# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_import")
load("@rules_xlsynth//:xls_toolchain.bzl", "copy_flat_files_to_directory", "xls_runtime_surface", "xls_shared_library_link", "xlsynth_artifact_config")

exports_files([
    {exported_files},
    "xlsynth_artifact_config.toml",
])

filegroup(
    name = "tools_root_files",
    srcs = [
        {tool_list},
    ],
)

copy_flat_files_to_directory(
    name = "dslx_stdlib",
    srcs = glob(["*.x"]),
    visibility = ["//visibility:public"],
)

{lib_file_rule}
{aot_runtime_rule}
{aot_runtime_source_rule}
{resolved_identity_rule}

xlsynth_artifact_config(
    name = "artifact_config",
    dso_name = "{libxls_name}",
    dslx_stdlib = ":dslx_stdlib",
    shared_library = ":libxls_file",
    static_aot_runtime = {static_aot_runtime},
    static_aot_runtime_link_config = {static_aot_runtime_link_config},
    visibility = ["//visibility:public"],
)

alias(
    name = "xlsynth_sys_artifact_config",
    actual = ":artifact_config",
    visibility = ["//visibility:public"],
)

alias(
    name = "xlsynth_sys_legacy_stdlib",
    actual = ":dslx_stdlib",
    visibility = ["//visibility:public"],
)

alias(
    name = "xlsynth_sys_legacy_dso",
    actual = ":libxls_file",
    visibility = ["//visibility:public"],
)

filegroup(
    name = "xlsynth_sys_runtime_files",
    srcs = [
        ":dslx_stdlib",
        ":libxls_runtime_files",
    ],
    visibility = ["//visibility:public"],
)

xls_shared_library_link(
    name = "xlsynth_sys_dep",
    runtime_files = ":xlsynth_sys_runtime_files",
    shared_library = ":libxls_file",
    visibility = ["//visibility:public"],
)

alias(
    name = "xlsynth_sys_link_dep",
    actual = ":libxls_link",
    visibility = ["//visibility:public"],
)

xls_runtime_surface(
    name = "runtime",
    dslx_stdlib = ":dslx_stdlib",
    libxls = ":libxls_file",
    xls_aot_runtime = {static_aot_runtime},
    runtime_files = [":libxls_runtime_files"],
    tools_root = ":tools_root_files",
    visibility = ["//visibility:public"],
)
""".format(
        exported_files = exported_files,
        tool_list = tool_list,
        libxls_name = libxls_name,
        lib_file_rule = lib_file_rule.strip(),
        aot_runtime_rule = aot_runtime_rule.strip(),
        aot_runtime_source_rule = aot_runtime_source_rule.strip(),
        resolved_identity_rule = resolved_identity_rule.strip(),
        static_aot_runtime = '":xls_aot_runtime_file"' if xls_aot_runtime_name else "None",
        static_aot_runtime_link_config = '":xls_aot_runtime_link_config_file"' if xls_aot_runtime_name else "None",
    )

def _string_attr_line(name, value):
    if not value:
        return ""
    return "    {} = {},\n".format(name, _quoted(value))

def _toolchain_build_file(
        repo_alias,
        runtime_repo_name,
        action_path,
        action_cargo_home,
        action_dyld_library_path,
        action_home,
        action_ld_library_path,
        action_rustup_home,
        artifact_source,
        allow_xls_pin_mismatch,
        emit_resolved_identity,
        host_driver_label,
        host_driver_provenance_label,
        installed_driver_root_prefix,
        local_driver_path,
        rustup_path,
        xlsynth_driver_git_revision,
        xlsynth_driver_version):
    action_env_attrs = "".join([
        _string_attr_line("action_cargo_home", action_cargo_home),
        _string_attr_line("action_dyld_library_path", action_dyld_library_path),
        _string_attr_line("action_home", action_home),
        _string_attr_line("action_ld_library_path", action_ld_library_path),
        _string_attr_line("action_rustup_home", action_rustup_home),
    ])
    driver_attrs = "".join([
        (
            "    resolved_identity = \"@{}//:resolved_identity_for_toolchain\",\n".format(runtime_repo_name) if emit_resolved_identity else ""
        ),
        _string_attr_line("host_driver", host_driver_label),
        _string_attr_line("host_driver_provenance", host_driver_provenance_label),
        _string_attr_line("installed_driver_root_prefix", installed_driver_root_prefix),
        _string_attr_line("local_driver_path", local_driver_path),
        _string_attr_line("rustup_path", rustup_path),
        _string_attr_line("xlsynth_driver_git_revision", xlsynth_driver_git_revision),
        _string_attr_line("xlsynth_driver_version", xlsynth_driver_version),
    ])
    return """# SPDX-License-Identifier: Apache-2.0

load("@rules_xlsynth//:xls_toolchain.bzl", "xls_bundle", "xls_toolchain", "xlsynth_driver_binary")

xlsynth_driver_binary(
    name = "xlsynth-driver",
    action_path = {action_path},
{action_env_attrs}    allow_xls_pin_mismatch = {allow_xls_pin_mismatch},
    artifact_source = {artifact_source},
    runtime = "@{runtime_repo_name}//:runtime",
{driver_attrs})

xls_bundle(
    name = "bundle",
    driver = ":xlsynth-driver",
    driver_supports_sv_enum_case_naming_policy = {driver_supports_sv_enum_case_naming_policy},
    driver_supports_sv_struct_field_ordering = {driver_supports_sv_struct_field_ordering},
    runtime = "@{runtime_repo_name}//:runtime",
    visibility = ["//visibility:public"],
)

alias(
    name = "{repo_alias}",
    actual = ":bundle",
    visibility = ["//visibility:public"],
)

xls_toolchain(
    name = "toolchain_impl",
    bundle = ":bundle",
)

toolchain(
    name = "toolchain",
    toolchain = ":toolchain_impl",
    toolchain_type = "@rules_xlsynth//:toolchain_type",
    visibility = ["//visibility:public"],
)
""".format(
        artifact_source = _quoted(artifact_source),
        action_env_attrs = action_env_attrs,
        action_path = _quoted(action_path),
        allow_xls_pin_mismatch = "True" if allow_xls_pin_mismatch else "False",
        driver_attrs = driver_attrs,
        driver_supports_sv_enum_case_naming_policy = "True" if _toolchain_driver_supports_sv_enum_case_naming_policy(artifact_source, local_driver_path, xlsynth_driver_git_revision, xlsynth_driver_version) else "False",
        driver_supports_sv_struct_field_ordering = "True" if _toolchain_driver_supports_sv_struct_field_ordering(artifact_source, local_driver_path, xlsynth_driver_git_revision, xlsynth_driver_version) else "False",
        repo_alias = repo_alias,
        runtime_repo_name = runtime_repo_name,
    )

def _driver_path_to_stage(repo_ctx):
    if not repo_ctx.attr.driver_path:
        return None
    driver_path = repo_ctx.path(repo_ctx.attr.driver_path)
    if driver_path.exists:
        return driver_path
    if repo_ctx.attr.required:
        fail("Missing required host xlsynth-driver at {}".format(driver_path))
    return None

def _driver_repo_impl(repo_ctx):
    link_name = "host_xlsynth-driver"
    provenance_name = _DRIVER_GIT_PROVENANCE_FILENAME
    driver_path = _driver_path_to_stage(repo_ctx)
    if driver_path == None:
        repo_ctx.file(link_name, "#!/bin/sh\nexit 127\n", executable = True)
    else:
        repo_ctx.symlink(driver_path, link_name)
    provenance_path = repo_ctx.path(repo_ctx.attr.driver_provenance_path)
    if repo_ctx.attr.driver_provenance_path and provenance_path.exists:
        repo_ctx.symlink(provenance_path, provenance_name)
    else:
        repo_ctx.file(provenance_name, "{}\n")
    repo_ctx.file(
        "BUILD.bazel",
        """# SPDX-License-Identifier: Apache-2.0

exports_files([
    "host_xlsynth-driver",
    "xlsynth-driver.provenance.json",
])
""",
    )

def _host_driver_path(toolchain):
    if toolchain.artifact_source == "local_paths":
        return toolchain.local_driver_path
    if toolchain.artifact_source in ("auto", "installed_only") and toolchain.installed_driver_root_prefix:
        if toolchain.xlsynth_driver_git_revision:
            return _installed_driver_path(toolchain.xlsynth_driver_git_revision, toolchain.installed_driver_root_prefix)
        if toolchain.xlsynth_driver_version:
            return _installed_driver_path(toolchain.xlsynth_driver_version, toolchain.installed_driver_root_prefix)
    return ""

def _host_driver_required(toolchain):
    return toolchain.artifact_source in ("local_paths", "installed_only")

def _host_driver_provenance_path(toolchain):
    driver_path = _host_driver_path(toolchain)
    if not driver_path or not toolchain.xlsynth_driver_git_revision:
        return ""
    return driver_path.rsplit("/", 1)[0] + "/" + _DRIVER_GIT_PROVENANCE_FILENAME

def _host_driver_label(toolchain, driver_name):
    if not _host_driver_path(toolchain):
        return ""
    return "@{}//:host_xlsynth-driver".format(driver_name)

def _host_driver_provenance_label(toolchain, driver_name):
    if not _host_driver_provenance_path(toolchain):
        return ""
    return "@{}//:{}".format(driver_name, _DRIVER_GIT_PROVENANCE_FILENAME)

def _materialize_bundle_args(repo_ctx, surface):
    args = [
        str(repo_ctx.path(Label("//:materialize_xls_bundle.py"))),
        "--repo-root",
        str(repo_ctx.path(".")),
        "--artifact-source",
        repo_ctx.attr.artifact_source,
        "--surface",
        surface,
    ]
    if repo_ctx.attr.xls_version:
        args.extend(["--xls-version", repo_ctx.attr.xls_version])
    if repo_ctx.attr.xls_git_revision:
        args.extend(["--xls-git-revision", repo_ctx.attr.xls_git_revision])
    if repo_ctx.attr.xlsynth_driver_version:
        args.extend(["--xlsynth-driver-version", repo_ctx.attr.xlsynth_driver_version])
    if repo_ctx.attr.xlsynth_driver_git_revision:
        args.extend(["--xlsynth-driver-git-revision", repo_ctx.attr.xlsynth_driver_git_revision])
    if repo_ctx.attr.emit_resolved_identity:
        args.append("--emit-resolved-identity")
    if repo_ctx.attr.allow_xls_pin_mismatch:
        args.append("--allow-xls-pin-mismatch")
    if repo_ctx.attr.installed_tools_root_prefix:
        args.extend(["--installed-tools-root-prefix", repo_ctx.attr.installed_tools_root_prefix])
    if repo_ctx.attr.installed_driver_root_prefix:
        args.extend(["--installed-driver-root-prefix", repo_ctx.attr.installed_driver_root_prefix])
    if repo_ctx.attr.local_tools_path:
        args.extend(["--local-tools-path", repo_ctx.attr.local_tools_path])
    if repo_ctx.attr.local_dslx_stdlib_path:
        args.extend(["--local-dslx-stdlib-path", repo_ctx.attr.local_dslx_stdlib_path])
    if repo_ctx.attr.local_driver_path:
        args.extend(["--local-driver-path", repo_ctx.attr.local_driver_path])
    if repo_ctx.attr.local_libxls_path:
        args.extend(["--local-libxls-path", repo_ctx.attr.local_libxls_path])
    if repo_ctx.attr.local_xls_aot_runtime_path:
        args.extend(["--local-xls-aot-runtime-path", repo_ctx.attr.local_xls_aot_runtime_path])
    if repo_ctx.attr.local_xls_aot_runtime_link_config_path:
        args.extend([
            "--local-xls-aot-runtime-link-config-path",
            repo_ctx.attr.local_xls_aot_runtime_link_config_path,
        ])
    if repo_ctx.attr.local_xls_aot_runtime_source_path:
        args.extend([
            "--local-xls-aot-runtime-source-path",
            repo_ctx.attr.local_xls_aot_runtime_source_path,
        ])
    return args

def _runtime_repo_impl(repo_ctx):
    python3 = repo_ctx.which("python3")
    if python3 == None:
        fail("python3 is required to materialize XLS bundles")
    result = repo_ctx.execute([str(python3)] + _materialize_bundle_args(repo_ctx, "runtime"), quiet = False)
    if result.return_code != 0:
        fail("Failed to materialize XLS runtime surface {}:\nstdout:\n{}\nstderr:\n{}".format(
            repo_ctx.name,
            result.stdout,
            result.stderr,
        ))
    metadata = _metadata_dict(repo_ctx, "runtime_metadata.txt")
    runtime_files = [
        runtime_file
        for runtime_file in metadata.get("libxls_runtime_files", "").split(",")
        if runtime_file
    ]
    runtime_aliases = [
        alias
        for alias in metadata.get("libxls_runtime_aliases", "").split(",")
        if alias
    ]
    repo_ctx.file(
        "BUILD.bazel",
        _runtime_build_file(
            libxls_name = metadata["libxls_name"],
            xls_aot_runtime_name = metadata["xls_aot_runtime_name"],
            xls_aot_runtime_link_config_name = metadata["xls_aot_runtime_link_config_name"],
            xls_aot_runtime_source_repo = metadata["xls_aot_runtime_source_repo"],
            runtime_files = runtime_files,
            runtime_aliases = runtime_aliases,
            resolved_identity = repo_ctx.path("resolved_identity.json").exists,
            toolchain_repo_name = repo_ctx.attr.toolchain_repo_name,
        ),
    )

def _toolchain_repo_impl(repo_ctx):
    rustup = repo_ctx.which("rustup")
    action_path = repo_ctx.os.environ.get("PATH", "")
    action_cargo_home = repo_ctx.os.environ.get("CARGO_HOME", "")
    action_dyld_library_path = repo_ctx.os.environ.get("DYLD_LIBRARY_PATH", "")
    action_home = repo_ctx.os.environ.get("HOME", "")
    action_ld_library_path = repo_ctx.os.environ.get("LD_LIBRARY_PATH", "")
    action_rustup_home = repo_ctx.os.environ.get("RUSTUP_HOME", "")
    repo_ctx.file(
        "BUILD.bazel",
        _toolchain_build_file(
            repo_alias = repo_ctx.attr.repo_alias,
            runtime_repo_name = repo_ctx.attr.runtime_repo_name,
            action_path = action_path,
            action_cargo_home = action_cargo_home,
            action_dyld_library_path = action_dyld_library_path,
            action_home = action_home,
            action_ld_library_path = action_ld_library_path,
            action_rustup_home = action_rustup_home,
            allow_xls_pin_mismatch = repo_ctx.attr.allow_xls_pin_mismatch,
            artifact_source = repo_ctx.attr.artifact_source,
            emit_resolved_identity = repo_ctx.attr.emit_resolved_identity,
            host_driver_label = repo_ctx.attr.host_driver_label,
            host_driver_provenance_label = repo_ctx.attr.host_driver_provenance_label,
            installed_driver_root_prefix = repo_ctx.attr.installed_driver_root_prefix,
            local_driver_path = repo_ctx.attr.local_driver_path,
            rustup_path = "" if rustup == None else str(rustup),
            xlsynth_driver_git_revision = repo_ctx.attr.xlsynth_driver_git_revision,
            xlsynth_driver_version = repo_ctx.attr.xlsynth_driver_version,
        ),
    )

_runtime_repo_attrs = {
    "allow_xls_pin_mismatch": attr.bool(),
    "artifact_source": attr.string(mandatory = True),
    "emit_resolved_identity": attr.bool(),
    "installed_driver_root_prefix": attr.string(),
    "installed_tools_root_prefix": attr.string(),
    "local_driver_path": attr.string(),
    "local_dslx_stdlib_path": attr.string(),
    "local_libxls_path": attr.string(),
    "local_xls_aot_runtime_path": attr.string(),
    "local_xls_aot_runtime_link_config_path": attr.string(),
    "local_xls_aot_runtime_source_path": attr.string(),
    "local_tools_path": attr.string(),
    "toolchain_repo_name": attr.string(mandatory = True),
    "xls_version": attr.string(),
    "xls_git_revision": attr.string(),
    "xlsynth_driver_git_revision": attr.string(),
    "xlsynth_driver_version": attr.string(),
}

_toolchain_repo_attrs = {
    "allow_xls_pin_mismatch": attr.bool(),
    "artifact_source": attr.string(mandatory = True),
    "emit_resolved_identity": attr.bool(),
    "host_driver_label": attr.string(),
    "host_driver_provenance_label": attr.string(),
    "installed_driver_root_prefix": attr.string(),
    "installed_tools_root_prefix": attr.string(),
    "local_driver_path": attr.string(),
    "local_dslx_stdlib_path": attr.string(),
    "local_libxls_path": attr.string(),
    "local_xls_aot_runtime_path": attr.string(),
    "local_xls_aot_runtime_link_config_path": attr.string(),
    "local_xls_aot_runtime_source_path": attr.string(),
    "local_tools_path": attr.string(),
    "repo_alias": attr.string(mandatory = True),
    "runtime_repo_name": attr.string(mandatory = True),
    "xls_version": attr.string(),
    "xls_git_revision": attr.string(),
    "xlsynth_driver_git_revision": attr.string(),
    "xlsynth_driver_version": attr.string(),
}

_driver_repo_attrs = {
    "driver_path": attr.string(),
    "driver_provenance_path": attr.string(),
    "required": attr.bool(),
}

_xls_runtime_repo = repository_rule(
    implementation = _runtime_repo_impl,
    attrs = _runtime_repo_attrs,
)

_xls_toolchain_repo = repository_rule(
    implementation = _toolchain_repo_impl,
    attrs = _toolchain_repo_attrs,
    environ = [
        "CARGO_HOME",
        "DYLD_LIBRARY_PATH",
        "HOME",
        "LD_LIBRARY_PATH",
        "PATH",
        "RUSTUP_HOME",
    ],
)

_xls_driver_repo = repository_rule(
    implementation = _driver_repo_impl,
    attrs = _driver_repo_attrs,
)

_toolchain_tag = tag_class(attrs = {
    "allow_xls_pin_mismatch": attr.bool(),
    "artifact_source": attr.string(mandatory = True),
    "emit_resolved_identity": attr.bool(),
    "installed_driver_root_prefix": attr.string(),
    "installed_tools_root_prefix": attr.string(),
    "local_driver_path": attr.string(),
    "local_dslx_stdlib_path": attr.string(),
    "local_libxls_path": attr.string(),
    "local_xls_aot_runtime_path": attr.string(),
    "local_xls_aot_runtime_link_config_path": attr.string(),
    "local_xls_aot_runtime_source_path": attr.string(),
    "local_tools_path": attr.string(),
    "name": attr.string(mandatory = True),
    "xls_version": attr.string(),
    "xls_git_revision": attr.string(),
    "xlsynth_driver_git_revision": attr.string(),
    "xlsynth_driver_version": attr.string(),
})

def _xls_extension_impl(module_ctx):
    for module in module_ctx.modules:
        for toolchain in module.tags.toolchain:
            runtime_name = _runtime_repo_name(toolchain.name)
            toolchain_name = _toolchain_repo_name(toolchain.name)
            driver_name = _driver_repo_name(toolchain.name)
            _xls_runtime_repo(
                name = runtime_name,
                allow_xls_pin_mismatch = toolchain.allow_xls_pin_mismatch,
                artifact_source = toolchain.artifact_source,
                emit_resolved_identity = toolchain.emit_resolved_identity,
                installed_driver_root_prefix = toolchain.installed_driver_root_prefix,
                installed_tools_root_prefix = toolchain.installed_tools_root_prefix,
                local_driver_path = toolchain.local_driver_path,
                local_dslx_stdlib_path = toolchain.local_dslx_stdlib_path,
                local_libxls_path = toolchain.local_libxls_path,
                local_xls_aot_runtime_path = toolchain.local_xls_aot_runtime_path,
                local_xls_aot_runtime_link_config_path = toolchain.local_xls_aot_runtime_link_config_path,
                local_xls_aot_runtime_source_path = toolchain.local_xls_aot_runtime_source_path,
                local_tools_path = toolchain.local_tools_path,
                toolchain_repo_name = toolchain_name,
                xls_version = toolchain.xls_version,
                xls_git_revision = toolchain.xls_git_revision,
                xlsynth_driver_git_revision = toolchain.xlsynth_driver_git_revision,
                xlsynth_driver_version = toolchain.xlsynth_driver_version,
            )
            _xls_driver_repo(
                name = driver_name,
                driver_path = _host_driver_path(toolchain),
                driver_provenance_path = _host_driver_provenance_path(toolchain),
                required = _host_driver_required(toolchain),
            )
            _xls_toolchain_repo(
                name = toolchain_name,
                allow_xls_pin_mismatch = toolchain.allow_xls_pin_mismatch,
                artifact_source = toolchain.artifact_source,
                emit_resolved_identity = toolchain.emit_resolved_identity,
                host_driver_label = _host_driver_label(toolchain, driver_name),
                host_driver_provenance_label = _host_driver_provenance_label(toolchain, driver_name),
                installed_driver_root_prefix = toolchain.installed_driver_root_prefix,
                installed_tools_root_prefix = toolchain.installed_tools_root_prefix,
                local_driver_path = toolchain.local_driver_path,
                local_dslx_stdlib_path = toolchain.local_dslx_stdlib_path,
                local_libxls_path = toolchain.local_libxls_path,
                local_xls_aot_runtime_path = toolchain.local_xls_aot_runtime_path,
                local_xls_aot_runtime_link_config_path = toolchain.local_xls_aot_runtime_link_config_path,
                local_xls_aot_runtime_source_path = toolchain.local_xls_aot_runtime_source_path,
                local_tools_path = toolchain.local_tools_path,
                repo_alias = toolchain_name,
                runtime_repo_name = runtime_name,
                xls_version = toolchain.xls_version,
                xls_git_revision = toolchain.xls_git_revision,
                xlsynth_driver_git_revision = toolchain.xlsynth_driver_git_revision,
                xlsynth_driver_version = toolchain.xlsynth_driver_version,
            )

xls = module_extension(
    implementation = _xls_extension_impl,
    tag_classes = {
        "toolchain": _toolchain_tag,
    },
)
