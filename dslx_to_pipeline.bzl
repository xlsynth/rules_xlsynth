# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_driver_path", "get_srcs_from_deps", "write_config_toml")

def _dslx_to_pipeline_impl(ctx):
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)

    srcs = get_srcs_from_deps(ctx)

    config_file = write_config_toml(ctx, xlsynth_tool_dir)

    # Flags for stdlib path
    flags_str = ''

    # Delay model flag
    if ctx.attr.delay_model:
        flags_str += ' --delay_model=' + ctx.attr.delay_model

    string_flags = ['pipeline_stages', 'input_valid_signal', 'output_valid_signal', 'module_name']
    for flag in string_flags:
        value = getattr(ctx.attr, flag)
        if value:
            flags_str += ' --{}={}'.format(flag, value)
    
    bool_flags = ['flop_inputs', 'flop_outputs']
    for flag in bool_flags:
        value = getattr(ctx.attr, flag)
        flags_str += ' --{}={}'.format(flag, str(value).lower())

    # Top entry function flag
    if ctx.attr.top:
        top_entry = ctx.attr.top
    else:
        fail("Please specify the 'top' entry function to use")

    # Define the output .sv file
    output_sv_file = ctx.outputs.sv_file
    output_sv_path = output_sv_file.path

    # Construct the command
    cmd = "{} --toolchain={} dslx2pipeline --dslx_input_file {} --dslx_top {} {} > {}".format(
        xlsynth_driver_file,
        config_file.path,
        srcs[0].path,
        top_entry,
        flags_str,
        output_sv_path,
    )

    ctx.actions.run(
        inputs = srcs + [config_file],
        outputs = [output_sv_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
        use_default_shell_env = True,
    )

    return DefaultInfo(
        files = depset(direct = [output_sv_file]),
    )

dslx_to_pipeline = rule(
    doc = "Convert a DSLX file to SystemVerilog type definitions",
    implementation = _dslx_to_pipeline_impl,
    attrs = {
        "deps": attr.label_list(
            doc = "The list of DSLX libraries to be tested.",
            providers = [DslxInfo],
        ),
        "delay_model": attr.string(
            doc = "The delay model to be used (e.g., 'asap7').",
            default = "",
        ),
        "input_valid_signal": attr.string(
            doc = "The pipeline load enable signal to use for input data",
        ),
        "output_valid_signal": attr.string(
            doc = "The pipeline load enable signal for output data",
        ),
        "pipeline_stages": attr.int(
            doc = "The number of pipeline stages.",
            default = 0,
        ),
        "flop_inputs": attr.bool(
            doc = "Whether to flop the input ports.",
            default = True,
        ),
        "flop_outputs": attr.bool(
            doc = "Whether to flop the output ports.",
            default = True,
        ),
        "module_name": attr.string(
            doc = "The module name to use in generation.",
            default = "",
        ),
        "top": attr.string(
            doc = "The top entry function within the dependency module.",
            mandatory = True,
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
    },
)

