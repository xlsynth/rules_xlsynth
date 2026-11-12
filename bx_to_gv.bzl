# SPDX-License-Identifier: Apache-2.0

"""Liberty mapping for BX designs."""

load(":bx_to_ir.bzl", "BX_COMPILE_ATTRS", "get_bx_compile_input")
load(":bx_toolchain.bzl", "require_bx_toolchain", "run_bx_driver")
load(":xls_toolchain.bzl", "get_selected_driver_toolchain")

def _bx_to_gv_impl(ctx):
    toolchain = get_selected_driver_toolchain(ctx)
    require_bx_toolchain(toolchain, "bx2gv")
    compile_input = get_bx_compile_input(ctx, toolchain)
    liberty = ctx.file.liberty_proto
    path_arguments = dict(compile_input.path_arguments)
    path_arguments["--liberty-proto"] = liberty
    run_bx_driver(
        ctx,
        toolchain,
        command = "bx2gv",
        inputs = compile_input.inputs + [liberty],
        arguments = compile_input.arguments,
        dslx_path = compile_input.dslx_path,
        path_arguments = path_arguments,
        working_directory = compile_input.working_directory,
        output = ctx.outputs.gv_file,
        output_flag = "--output",
        mnemonic = "BxToGv",
    )
    return DefaultInfo(files = depset([ctx.outputs.gv_file]))

bx_to_gv = rule(
    doc = "Map a BX design to gate-level Verilog using a normalized Liberty library.",
    implementation = _bx_to_gv_impl,
    attrs = dict(BX_COMPILE_ATTRS, liberty_proto = attr.label(
        allow_single_file = [".proto", ".textproto", ".proto.gz", ".textproto.gz"],
        doc = "Normalized Liberty proto with combinational cells and flip-flops.",
        mandatory = True,
    )),
    outputs = {"gv_file": "%{name}.gv"},
    toolchains = ["//:toolchain_type"],
)
