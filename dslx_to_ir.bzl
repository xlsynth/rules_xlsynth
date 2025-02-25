# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_driver_path", "get_srcs_from_deps", "write_config_toml", "mangle_dslx_name")
load(":ir_provider.bzl", "IrInfo")

def _dslx_to_ir_impl(ctx):
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)

    srcs = get_srcs_from_deps(ctx)

    config_file = write_config_toml(ctx, xlsynth_tool_dir)

    cmd = "{driver} --toolchain={toolchain} dslx2ir --dslx_input_file={src} --dslx_top={top} > {output}".format(
        driver = xlsynth_driver_file,
        toolchain = config_file.path,
        src = srcs[0].path,
        top = ctx.attr.top,
        output = ctx.outputs.ir_file.path,
    )

    ctx.actions.run(
        inputs = srcs + [config_file],
        outputs = [ctx.outputs.ir_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
        use_default_shell_env = True,
        progress_message = "Generating IR for DSLX",
        mnemonic = "DSLX2IR",
    )

    ir_top = mangle_dslx_name(srcs[0].basename, ctx.attr.top)

    # Now we optimize that (unoptimized) IR file.

    cmd = "{driver} --toolchain={toolchain} ir2opt {src} --top {ir_top} > {output}".format(
        driver = xlsynth_driver_file,
        toolchain = config_file.path,
        src = ctx.outputs.ir_file.path,
        ir_top = ir_top,
        output = ctx.outputs.opt_ir_file.path,
    )

    ctx.actions.run(
        inputs = [ctx.outputs.ir_file] + [config_file],
        outputs = [ctx.outputs.opt_ir_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
        use_default_shell_env = True,
        progress_message = "Optimizing IR",
        mnemonic = "IR2OPT",
    )

    return IrInfo(
        ir_file = ctx.outputs.ir_file,
        opt_ir_file = ctx.outputs.opt_ir_file,
    )

dslx_to_ir = rule(
    doc = "Convert a DSLX file to IR",
    implementation = _dslx_to_ir_impl,
    attrs = {
        "deps": attr.label_list(
            doc = "The list of DSLX libraries.",
            providers = [DslxInfo],
        ),
        "top": attr.string(
            doc = "The top-level DSLX module to be converted to IR.",
            mandatory = True,
        ),
    },
    outputs = {
        "ir_file": "%{name}.ir",
        "opt_ir_file": "%{name}.opt.ir",
    },
)
