# SPDX-License-Identifier: Apache-2.0

"""SystemVerilog emission for XLS block IR."""

load(":block_ir_provider.bzl", "BlockIrInfo")
load(":bx_toolchain.bzl", "bx_runtime_env", "require_bx_toolchain", "run_bx_driver")
load(
    ":xls_toolchain.bzl",
    "XlsArtifactBundleInfo",
    "get_selected_driver_toolchain",
    "get_tool_artifact_inputs",
)

def _block_ir_to_sv_impl(ctx):
    toolchain = get_selected_driver_toolchain(ctx)
    require_bx_toolchain(toolchain, "block2sv")

    ir = ctx.attr.ir
    top = ctx.attr.top
    if BlockIrInfo in ir:
        source = ir[BlockIrInfo].ir_file
        top = top or ir[BlockIrInfo].top
    else:
        files = ir[DefaultInfo].files.to_list()
        if len(files) != 1 or files[0].is_directory or files[0].extension != "ir":
            fail("ir must provide BlockIrInfo or exactly one .ir file")
        source = files[0]

    lowered_ir = ctx.actions.declare_file(ctx.label.name + ".lowered.block.ir")
    top_args = ["--top=" + top] if top else []

    # Keep the authored register graph. Only lower constructs the emitter
    # cannot yet translate directly.
    ctx.actions.run(
        inputs = [source] + get_tool_artifact_inputs(toolchain, "opt_main"),
        outputs = [lowered_ir],
        executable = toolchain.tools_path + "/opt_main",
        arguments = [
            source.path,
            "--passes=[map_inlining loop_unroll inlining]",
            "--output_path=" + lowered_ir.path,
        ] + top_args,
        env = bx_runtime_env(toolchain.runtime_library_path),
        mnemonic = "BlockIrLower",
    )

    arguments = [lowered_ir.path] + top_args
    if ctx.attr.module_name:
        arguments.append("--module-name=" + ctx.attr.module_name)
    run_bx_driver(
        ctx,
        toolchain,
        command = "block2sv",
        inputs = [lowered_ir],
        arguments = arguments,
        output = ctx.outputs.sv_file,
        mnemonic = "BlockIrToSv",
    )
    return DefaultInfo(files = depset([ctx.outputs.sv_file]))

block_ir_to_sv = rule(
    doc = "Emit a SystemVerilog file from a package containing XLS blocks.",
    implementation = _block_ir_to_sv_impl,
    attrs = {
        "ir": attr.label(
            allow_files = [".ir"],
            doc = "A BlockIrInfo target or a single package-form XLS IR file.",
            mandatory = True,
        ),
        "module_name": attr.string(doc = "Override the emitted top module name."),
        "top": attr.string(doc = "Select a block other than the package or provider's top."),
        "xls_bundle": attr.label(
            doc = "Optional XLS bundle override.",
            providers = [XlsArtifactBundleInfo],
        ),
    },
    outputs = {"sv_file": "%{name}.sv"},
    toolchains = ["//:toolchain_type"],
)
