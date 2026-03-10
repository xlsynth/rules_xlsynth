# SPDX-License-Identifier: Apache-2.0

load(":ir_provider.bzl", "IrInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "require_driver_toolchain")


def _ir_to_gates_impl(ctx):
    ir_info = ctx.attr.ir_src[IrInfo]
    ir_file_to_use = ir_info.opt_ir_file
    gates_file = ctx.outputs.gates_file
    metrics_file = ctx.outputs.metrics_json

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = require_driver_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "ir_to_gates")

    ctx.actions.run(
        inputs = [ir_file_to_use, toolchain_file] + get_driver_artifact_inputs(toolchain),
        executable = runner,
        outputs = [gates_file, metrics_file],
        arguments = [
            "driver",
            "--driver_path",
            toolchain.driver_path,
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "--toolchain",
            toolchain_file.path,
            "--stdout_path",
            gates_file.path,
            "ir2gates",
            "--fraig={}".format("true" if ctx.attr.fraig else "false"),
            "--output_json={}".format(metrics_file.path),
            ir_file_to_use.path,
        ],
        use_default_shell_env = False,
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
    },
    outputs = {
        "gates_file": "%{name}.txt",
        "metrics_json": "%{name}.json",
    },
    toolchains = ["//:toolchain_type"],
)
