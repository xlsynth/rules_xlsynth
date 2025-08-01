# SPDX-License-Identifier: Apache-2.0

load(":helpers.bzl", "get_driver_path", "write_config_toml")
load(":ir_provider.bzl", "IrInfo")

def _ir_to_gates_impl(ctx):
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)

    ir_info = ctx.attr.ir_src[IrInfo]
    # Use the optimized IR file by default, like ir_to_delay_info does implicitly
    # If needed, we could add a flag like 'use_unopt_ir' similar to ir_to_delay_info
    ir_file_to_use = ir_info.opt_ir_file
    gates_file = ctx.outputs.gates_file
    metrics_file = ctx.outputs.metrics_json

    config_file = write_config_toml(ctx, xlsynth_tool_dir)

    cmd = "{driver} --toolchain={toolchain} ir2gates --fraig={fraig} --output_json={metrics} {src} > {output}".format(
        driver = xlsynth_driver_file,
        toolchain = config_file.path,
        src = ir_file_to_use.path,
        output = gates_file.path,
        metrics = metrics_file.path,
        fraig = "true" if ctx.attr.fraig else "false",
    )

    ctx.actions.run(
        inputs = [ir_file_to_use] + [config_file],
        outputs = [gates_file, metrics_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
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
    },
    outputs = {
        "gates_file": "%{name}.txt",
        "metrics_json": "%{name}.json",
    },
)
