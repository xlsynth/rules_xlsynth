# SPDX-License-Identifier: Apache-2.0

load(":ir_provider.bzl", "IrInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "require_driver_toolchain")


def _ir_to_delay_info_impl(ctx):
    opt_ir_file = ctx.attr.ir[IrInfo].ir_file if ctx.attr.use_unopt_ir else ctx.attr.ir[IrInfo].opt_ir_file
    output_file = ctx.outputs.delay_info

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = require_driver_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "ir_to_delay_info")

    ctx.actions.run(
        inputs = [opt_ir_file, toolchain_file] + get_driver_artifact_inputs(toolchain, ["delay_info_main"]),
        executable = runner,
        outputs = [output_file],
        arguments = [
            "driver",
            "--driver_path",
            toolchain.driver_path,
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "--toolchain",
            toolchain_file.path,
            "--stdout_path",
            output_file.path,
            "ir2delayinfo",
            "--delay_model",
            ctx.attr.delay_model,
            opt_ir_file.path,
            ctx.attr.top,
        ],
        use_default_shell_env = False,
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
    },
    outputs = {
        "delay_info": "%{name}.txt",
    },
    toolchains = ["//:toolchain_type"],
)
