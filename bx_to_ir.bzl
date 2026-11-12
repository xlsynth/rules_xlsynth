# SPDX-License-Identifier: Apache-2.0

"""Compile BX into XLS block IR."""

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

def _source_import_root(src, runfiles):
    # The short path of an external file starts with the runfiles prefix
    # ../<repository>/, while the rest is the repository-relative source path.
    relative_path = src.short_path
    if relative_path.startswith("../"):
        _, repository, relative_path = relative_path.split("/", 2)
        if runfiles:
            return "../" + repository
    if runfiles:
        return "."
    return src.path[:-len(relative_path)].rstrip("/") or "."

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
        A struct containing inputs and arguments lists.
    """
    bx = ctx.attr.lib[BxInfo]
    inputs = bx.transitive_srcs.to_list()

    # Preserve explicit search-path precedence, then allow imports qualified
    # from the roots of declared source files. The driver adds the root
    # module's own directory after these search paths.
    roots = {path: None for path in toolchain.dslx_path}
    for path in sorted({_source_import_root(src, runfiles): None for src in inputs}):
        roots[path] = None

    arguments = [
        bx.root.short_path if runfiles else bx.root.path,
        "--dslx-path",
        ";".join(roots.keys()),
        "--warnings-as-errors=" + str(ctx.attr.warnings_as_errors).lower(),
    ]
    if runfiles:
        stdlib = getattr(toolchain, "dslx_stdlib", None)

        # The toolchain TOML uses an execroot path for the standard library.
        arguments.extend(["--dslx-stdlib-path", stdlib.short_path if stdlib else toolchain.dslx_stdlib_path])
    if ctx.attr.reset_active_low:
        arguments.append("--reset-active-low")
    if ctx.attr.link_ir:
        link_ir = _link_ir_file(ctx)
        arguments.extend(["--link-ir", link_ir.short_path if runfiles else link_ir.path])
        inputs.append(link_ir)

    return struct(inputs = inputs, arguments = arguments)

def get_bx_compile_input(ctx, toolchain):
    """Adds design top and reset options to the shared BX source inputs.

    Args:
        ctx: Rule context with BX_COMPILE_ATTRS.
        toolchain: Selected XLS driver toolchain.

    Returns:
        A struct containing inputs and arguments lists.
    """
    if not ctx.attr.top:
        fail("top must be a nonempty block name", attr = "top")
    source = get_bx_source_input(ctx, toolchain)
    arguments = source.arguments + ["--top", ctx.attr.top]
    if ctx.attr.reset_asynchronous:
        arguments.append("--reset-asynchronous")
    return struct(inputs = source.inputs, arguments = arguments)

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
