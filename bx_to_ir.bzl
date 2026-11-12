# SPDX-License-Identifier: Apache-2.0

"""Compile BX into XLS block IR."""

load("@bazel_skylib//lib:paths.bzl", "paths")
load(":block_ir_provider.bzl", "BlockIrInfo")
load(":bx_provider.bzl", "BxInfo")
load(":bx_toolchain.bzl", "require_bx_toolchain", "run_bx_driver")
load(":ir_provider.bzl", "IrInfo")
load(":xls_toolchain.bzl", "XlsArtifactBundleInfo", "get_selected_driver_toolchain")

BX_SOURCE_ATTRS = {
    "lib": attr.label(
        doc = "BX library containing the root module.",
        providers = [BxInfo],
        mandatory = True,
    ),
    "link_ir": attr.label(
        doc = "Optional IR package providing BX extern declarations. An IrInfo target supplies its unoptimized package.",
        allow_files = [".ir"],
    ),
    "reset_active_low": attr.bool(
        doc = "Use active-low reset throughout the compiled block hierarchy.",
    ),
    "warnings_as_errors": attr.bool(
        doc = "Treat BX warnings as compilation errors.",
        default = True,
    ),
    "xls_bundle": attr.label(
        doc = "Optional XLS bundle override.",
        providers = [XlsArtifactBundleInfo],
    ),
}

BX_COMPILE_ATTRS = dict(
    BX_SOURCE_ATTRS,
    reset_asynchronous = attr.bool(
        doc = "Use asynchronous reset throughout the compiled block hierarchy.",
    ),
    top = attr.string(
        doc = "Name of the BX block to select as the design top.",
        mandatory = True,
    ),
)

def _source_import_root(src, logical_paths):
    # The short path of an external file starts with the runfiles prefix
    # ../<repository>/, while the rest is the repository-relative source path.
    relative_path = src.short_path
    repository = None
    if relative_path.startswith("../"):
        _, repository, relative_path = relative_path.split("/", 2)
    if logical_paths:
        path = "../" + repository if repository else "."
    else:
        path = src.path[:-len(relative_path)].rstrip("/") or "."
    return struct(repository = repository, path = path)

def _configured_import_path(path, external_roots):
    parts = paths.normalize(path).split("/", 2)
    if len(parts) < 2 or parts[0] not in ["external", ".."] or parts[1] not in external_roots:
        return path
    root = external_roots[parts[1]]
    return paths.join(root, parts[2]) if len(parts) == 3 else root

def _stage_bx_sources(ctx, srcs):
    tree = ctx.actions.declare_directory(ctx.label.name + ".bx_sources")
    copies = ctx.actions.args()
    copies.use_param_file("%s", use_always = True)
    copies.set_param_file_format("multiline")
    for src in srcs:
        copies.add(src.path)
        copies.add(paths.normalize(paths.join("_main", src.short_path)))
    ctx.actions.run_shell(
        inputs = srcs,
        outputs = [tree],
        arguments = [tree.path, copies],
        command = """
            set -eu
            mkdir -p "$1/_main"
            while IFS= read -r source && IFS= read -r destination; do
                destination="$1/$destination"
                mkdir -p "${destination%/*}"
                cp "$source" "$destination"
            done < "$2"
        """,
        mnemonic = "BxStageSources",
    )
    return tree

def _link_ir_file(ctx):
    target = ctx.attr.link_ir
    if BlockIrInfo in target:
        return target[BlockIrInfo].ir_file
    if IrInfo in target:
        return target[IrInfo].ir_file
    files = ctx.files.link_ir
    if len(files) != 1 or files[0].is_directory or files[0].extension != "ir":
        fail("link_ir must provide one .ir file, BlockIrInfo, or IrInfo", attr = "link_ir")
    return files[0]

def get_bx_source_input(ctx, toolchain, runfiles = False):
    """Returns the declared inputs and shared driver arguments for a BX design.

    Args:
        ctx: Rule context with BX_SOURCE_ATTRS.
        toolchain: Selected XLS driver toolchain.
        runfiles: Use paths relative to the workspace runfiles directory.

    Returns:
        A struct containing inputs, driver arguments, and the action working directory.
    """
    bx = ctx.attr.lib[BxInfo]
    srcs = bx.transitive_srcs.to_list()
    inputs = srcs
    working_directory = None
    if not runfiles and any([not src.is_source for src in srcs]):
        # Match the test runfiles layout so implicit and explicit imports
        # resolve identically when Bazel generates part of the source tree.
        tree = _stage_bx_sources(ctx, srcs)
        inputs = [tree]
        working_directory = paths.join(tree.path, "_main")
    logical_paths = runfiles or working_directory != None

    # Preserve explicit search-path precedence, then allow imports qualified
    # from the roots of declared source files.
    source_roots = {}
    external_roots = {}
    for src in srcs:
        root = _source_import_root(src, logical_paths)
        source_roots[root.path] = None
        if root.repository:
            external_roots[root.repository] = root.path
    roots = {_configured_import_path(path, external_roots): None for path in toolchain.dslx_path}
    for path in sorted(source_roots):
        roots[path] = None

    arguments = [
        bx.root.short_path if logical_paths else bx.root.path,
        "--dslx-path",
        ";".join(roots.keys()),
        "--warnings-as-errors=" + str(ctx.attr.warnings_as_errors).lower(),
    ]
    path_arguments = {}
    if runfiles:
        # The toolchain TOML uses an execroot path for the standard library.
        arguments.extend(["--dslx-stdlib-path", toolchain.dslx_stdlib.short_path])
    elif working_directory:
        path_arguments["--dslx-stdlib-path"] = toolchain.dslx_stdlib
    if ctx.attr.reset_active_low:
        arguments.append("--reset-active-low")
    if ctx.attr.link_ir:
        link_ir = _link_ir_file(ctx)
        if runfiles:
            arguments.extend(["--link-ir", link_ir.short_path])
        else:
            path_arguments["--link-ir"] = link_ir
        inputs.append(link_ir)

    return struct(
        inputs = inputs,
        arguments = arguments,
        path_arguments = path_arguments,
        working_directory = working_directory,
    )

def get_bx_compile_input(ctx, toolchain):
    """Adds design top and reset options to the shared BX source inputs.

    Args:
        ctx: Rule context with BX_COMPILE_ATTRS.
        toolchain: Selected XLS driver toolchain.

    Returns:
        A struct containing inputs, driver arguments, and the action working directory.
    """
    if not ctx.attr.top:
        fail("top must be a nonempty block name", attr = "top")
    source = get_bx_source_input(ctx, toolchain)
    arguments = source.arguments + ["--top", ctx.attr.top]
    if ctx.attr.reset_asynchronous:
        arguments.append("--reset-asynchronous")
    return struct(
        inputs = source.inputs,
        arguments = arguments,
        path_arguments = source.path_arguments,
        working_directory = source.working_directory,
    )

def _bx_to_ir_impl(ctx):
    toolchain = get_selected_driver_toolchain(ctx)
    require_bx_toolchain(toolchain, "bx2ir")
    compile_input = get_bx_compile_input(ctx, toolchain)
    ir_file = ctx.outputs.ir_file
    run_bx_driver(
        ctx,
        toolchain,
        command = "bx2ir",
        inputs = compile_input.inputs,
        arguments = compile_input.arguments,
        path_arguments = compile_input.path_arguments,
        working_directory = compile_input.working_directory,
        output = ir_file,
        mnemonic = "BX2IR",
    )
    return [
        BlockIrInfo(ir_file = ir_file, top = ctx.attr.top),
        DefaultInfo(files = depset([ir_file])),
    ]

bx_to_ir = rule(
    doc = "Compile a BX design to XLS block IR.",
    implementation = _bx_to_ir_impl,
    attrs = BX_COMPILE_ATTRS,
    outputs = {"ir_file": "%{name}.block.ir"},
    provides = [BlockIrInfo],
    toolchains = ["//:toolchain_type"],
)
