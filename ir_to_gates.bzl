# SPDX-License-Identifier: Apache-2.0

load(":ir_provider.bzl", "IrInfo")


def _ir_to_gates_impl(ctx):
    ir_info = ctx.attr.ir_src[IrInfo]
    ir_file_to_use = ir_info.opt_ir_file
    gates_file = ctx.outputs.gates_file
    metrics_file = ctx.outputs.metrics_json

    ctx.actions.run(
        inputs = [ir_file_to_use, ctx.file._runner],
        outputs = [gates_file, metrics_file],
        arguments = [
            "python3",
            ctx.file._runner.path,
            "driver",
            "ir2gates",
            "--fraig={}".format("true" if ctx.attr.fraig else "false"),
            "--output_json={}".format(metrics_file.path),
            ir_file_to_use.path,
            "--stdout_out",
            gates_file.path,
        ],
        executable = "/usr/bin/env",
        use_default_shell_env = True,
        progress_message = "Generating gate-level analysis for IR",
        mnemonic = "IR2GATES",
    )

    return DefaultInfo(
        files = depset(direct = [gates_file, metrics_file]),
    )


ir_to_gates = rule(
    doc = "Convert an IR file to gate-level analysis",
    implementation = _ir_to_gates_impl,
    attrs = {
        "ir_src": attr.label(
            doc = "The IR target providing the source IR file.",
            providers = [IrInfo],
            mandatory = True,
        ),
        "fraig": attr.bool(
            doc = "If true, perform \"fraig\" optimization; can be slow when gate graph is large.",
            default = True,
        ),
        "_runner": attr.label(
            default = Label("//:xlsynth_runner.py"),
            allow_single_file = True,
        ),
    },
    outputs = {
        "gates_file": "%{name}.txt",
        "metrics_json": "%{name}.json",
    },
)
