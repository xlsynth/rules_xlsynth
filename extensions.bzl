_TOOL_BINARIES = [
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


def _metadata_dict(repo_ctx):
    metadata = {}
    metadata_path = repo_ctx.path("bundle_metadata.txt")
    if not metadata_path.exists:
        fail("Missing bundle metadata at {}".format(metadata_path))
    for line in repo_ctx.read("bundle_metadata.txt").splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        metadata[key] = value
    return metadata


def _bundle_build_file(libxls_name, driver_supports):
    tool_list = ",\n        ".join(['"{}"'.format(name) for name in _TOOL_BINARIES])
    lib_target = libxls_name
    lib_file_rule = """
filegroup(
    name = "libxls_file",
    srcs = ["{lib_target}"],
    visibility = ["//visibility:public"],
)
cc_import(
    name = "libxls",
    shared_library = ":libxls_file",
    visibility = ["//visibility:public"],
)
xls_shared_library_link(
    name = "libxls_link",
    shared_library = ":libxls_file",
    visibility = ["//visibility:public"],
)
""".format(lib_target = lib_target)
    if libxls_name.endswith(".dylib"):
        lib_file_rule = """
patch_dylib(
    name = "libxls_patched",
    src = "{lib_target}",
    out = "libxls_patched.dylib",
)
filegroup(
    name = "libxls_file",
    srcs = [":libxls_patched"],
    visibility = ["//visibility:public"],
)
cc_import(
    name = "libxls",
    shared_library = ":libxls_file",
    visibility = ["//visibility:public"],
)
xls_shared_library_link(
    name = "libxls_link",
    shared_library = ":libxls_file",
    visibility = ["//visibility:public"],
)
""".format(lib_target = lib_target)
    return """# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_import")
load("@rules_xlsynth//:xls_toolchain.bzl", "copy_flat_files_to_directory", "patch_dylib", "xls_bundle", "xls_shared_library_link", "xls_toolchain")

exports_files([
    {tool_list},
    "xlsynth-driver",
    "{libxls_name}",
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

xls_bundle(
    name = "bundle",
    driver = ":xlsynth-driver",
    driver_supports_sv_enum_case_naming_policy = {driver_supports},
    dslx_stdlib = ":dslx_stdlib",
    libxls = ":libxls_file",
    tools_root = ":tools_root_files",
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
        tool_list = tool_list,
        libxls_name = libxls_name,
        lib_file_rule = lib_file_rule.strip(),
        driver_supports = "True" if driver_supports else "False",
    )


def _bundle_repo_impl(repo_ctx):
    python3 = repo_ctx.which("python3")
    if python3 == None:
        fail("python3 is required to materialize XLS bundles")
    args = [
        str(python3),
        str(repo_ctx.path(Label("//:materialize_xls_bundle.py"))),
        "--repo-root",
        str(repo_ctx.path(".")),
        "--artifact-source",
        repo_ctx.attr.artifact_source,
    ]
    if repo_ctx.attr.xls_version:
        args.extend(["--xls-version", repo_ctx.attr.xls_version])
    if repo_ctx.attr.xlsynth_driver_version:
        args.extend(["--xlsynth-driver-version", repo_ctx.attr.xlsynth_driver_version])
    if repo_ctx.attr.local_tools_path:
        args.extend(["--local-tools-path", repo_ctx.attr.local_tools_path])
    if repo_ctx.attr.local_dslx_stdlib_path:
        args.extend(["--local-dslx-stdlib-path", repo_ctx.attr.local_dslx_stdlib_path])
    if repo_ctx.attr.local_driver_path:
        args.extend(["--local-driver-path", repo_ctx.attr.local_driver_path])
    if repo_ctx.attr.local_libxls_path:
        args.extend(["--local-libxls-path", repo_ctx.attr.local_libxls_path])
    result = repo_ctx.execute(args, quiet = False)
    if result.return_code != 0:
        fail("Failed to materialize XLS bundle {}:\nstdout:\n{}\nstderr:\n{}".format(
            repo_ctx.name,
            result.stdout,
            result.stderr,
        ))
    metadata = _metadata_dict(repo_ctx)
    repo_ctx.file(
        "BUILD.bazel",
        _bundle_build_file(
            libxls_name = metadata["libxls_name"],
            driver_supports = metadata["driver_supports_sv_enum_case_naming_policy"] == "true",
        ),
    )


_xls_bundle_repo = repository_rule(
    implementation = _bundle_repo_impl,
    attrs = {
        "artifact_source": attr.string(mandatory = True),
        "local_driver_path": attr.string(),
        "local_dslx_stdlib_path": attr.string(),
        "local_libxls_path": attr.string(),
        "local_tools_path": attr.string(),
        "xls_version": attr.string(),
        "xlsynth_driver_version": attr.string(),
    },
)

_toolchain_tag = tag_class(attrs = {
    "artifact_source": attr.string(mandatory = True),
    "local_driver_path": attr.string(),
    "local_dslx_stdlib_path": attr.string(),
    "local_libxls_path": attr.string(),
    "local_tools_path": attr.string(),
    "name": attr.string(mandatory = True),
    "xls_version": attr.string(),
    "xlsynth_driver_version": attr.string(),
})


def _xls_extension_impl(module_ctx):
    for module in module_ctx.modules:
        for toolchain in module.tags.toolchain:
            _xls_bundle_repo(
                name = toolchain.name,
                artifact_source = toolchain.artifact_source,
                local_driver_path = toolchain.local_driver_path,
                local_dslx_stdlib_path = toolchain.local_dslx_stdlib_path,
                local_libxls_path = toolchain.local_libxls_path,
                local_tools_path = toolchain.local_tools_path,
                xls_version = toolchain.xls_version,
                xlsynth_driver_version = toolchain.xlsynth_driver_version,
            )


xls = module_extension(
    implementation = _xls_extension_impl,
    tag_classes = {
        "toolchain": _toolchain_tag,
    },
)
