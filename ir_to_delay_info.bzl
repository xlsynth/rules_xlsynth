# SPDX-License-Identifier: Apache-2.0

load(":ir_provider.bzl", "IrInfo")


def _ir_to_delay_info_impl(ctx):
    opt_ir_file = ctx.attr.ir[IrInfo].ir_file if ctx.attr.use_unopt_ir else ctx.attr.ir[IrInfo].opt_ir_file
    output_file = ctx.outputs.delay_info

    args = [
        "python3",
        ctx.file._runner.path,
        "driver",
        "ir2delayinfo",
        "--delay_model={}".format(ctx.attr.delay_model),
        opt_ir_file.path,
        ctx.attr.top,
    ]

    ctx.actions.run(
        inputs = [opt_ir_file, ctx.file._runner],
        outputs = [output_file],
        arguments = args + ["--stdout_out", output_file.path],
        executable = "/usr/bin/env",
        use_default_shell_env = True,
    )

    return DefaultInfo(
        files = depset(direct = [output_file]),
    )


ir_to_delay_info = rule(
    doc = "Convert an IR file to delay info",
    implementation = _ir_to_delay_info_impl,
    attrs = {
        "ir": attr.label(
            doc = "The IR file to convert to delay info.",
            providers = [IrInfo],
        ),
        "top": attr.string(
            doc = "The top-level DSLX module to be converted to IR.",
            mandatory = True,
        ),
        "delay_model": attr.string(
            doc = "The delay model to use.",
            mandatory = True,
        ),
        "use_unopt_ir": attr.bool(
            doc = "Whether to use the unoptimized IR file instead of optimized IR file.",
            default = False,
        ),
        "_runner": attr.label(
            default = Label("//:xlsynth_runner.py"),
            allow_single_file = True,
        ),
    },
    outputs = {
        "delay_info": "%{name}.txt",
    },
)
