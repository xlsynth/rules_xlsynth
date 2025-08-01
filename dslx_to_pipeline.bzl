# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_driver_path", "get_srcs_from_deps", "write_config_toml")

def _dslx_to_pipeline_impl(ctx):
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)

    srcs = get_srcs_from_deps(ctx)

    config_file = write_config_toml(ctx, xlsynth_tool_dir)

    # Flags for stdlib path
    flags_str = ""

    # Delay model flag (required)
    flags_str += " --delay_model=" + ctx.attr.delay_model

    # Forward string-valued flags when a non-empty value is provided.
    for flag in ["input_valid_signal", "output_valid_signal", "module_name"]:
        value = getattr(ctx.attr, flag)
        if value:
            flags_str += " --{}={}".format(flag, value)

    # Forward integer-valued timing flags when >0.
    if ctx.attr.pipeline_stages > 0:
        flags_str += " --pipeline_stages={}".format(ctx.attr.pipeline_stages)
    if ctx.attr.clock_period_ps > 0:
        flags_str += " --clock_period_ps={}".format(ctx.attr.clock_period_ps)

    # Validate that either pipeline_stages or clock_period_ps is specified (>0).
    if ctx.attr.pipeline_stages == 0 and ctx.attr.clock_period_ps == 0:
        fail("Please specify either 'pipeline_stages' (>0) or 'clock_period_ps' (>0)")

    # Boolean flags that are forwarded verbatim to the driver as
    #   --<flag>=true|false
    # Note that we ALWAYS forward these, even if they are at their default
    # value; this documents the chosen default in the command line.
    bool_flags = [
        "flop_inputs",
        "flop_outputs",
        "reset_data_path",
    ]
    for flag in bool_flags:
        value = getattr(ctx.attr, flag)
        flags_str += " --{}={}".format(flag, str(value).lower())

    # If the attribute is explicitly set ("true" or "false") forward it to
    # override whatever value may be present in the toolchain config.
    if ctx.attr.add_invariant_assertions != "":
        flags_str += " --add_invariant_assertions={}".format(ctx.attr.add_invariant_assertions)

    # Top entry function flag
    if ctx.attr.top:
        top_entry = ctx.attr.top
    else:
        fail("Please specify the 'top' entry function to use")

    if ctx.attr.reset:
        flags_str += " --reset={}".format(ctx.attr.reset)

    # Define the output .sv file
    output_sv_file = ctx.outputs.sv_file
    output_sv_path = output_sv_file.path
    output_unopt_ir_file = ctx.outputs.unopt_ir_file
    output_unopt_ir_path = output_unopt_ir_file.path
    output_opt_ir_file = ctx.outputs.opt_ir_file
    output_opt_ir_path = output_opt_ir_file.path

    # Construct the command
    cmd = "{} --toolchain={} dslx2pipeline --dslx_input_file={} --dslx_top={} --output_unopt_ir={} --output_opt_ir={} {} > {}".format(
        xlsynth_driver_file,
        config_file.path,
        srcs[0].path,
        top_entry,
        output_unopt_ir_path,
        output_opt_ir_path,
        flags_str,
        output_sv_path,
    )

    ctx.actions.run(
        inputs = srcs + [config_file],
        outputs = [output_sv_file, output_unopt_ir_file, output_opt_ir_file],
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
            mandatory = True,
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
        "clock_period_ps": attr.int(
            doc = "Target clock period in picoseconds (alternative to pipeline_stages).",
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
        "reset_data_path": attr.bool(
            doc = "Whether to generate reset logic for data-path registers.",
            default = True,
        ),
        # Tri-state: "true" / "false" / "" (unspecified). When non-empty the
        # provided value overrides the setting in the TOML (which may come from
        # XLSYNTH_ADD_INVARIANT_ASSERTIONS). Using a string lets us detect the
        # unspecified case, which is not possible with attr.bool.
        "add_invariant_assertions": attr.string(
            doc = "Override for invariant assertions generation: 'true', 'false', or leave empty to use toolchain default.",
            default = "",
            values = ["true", "false", ""],
        ),
        "module_name": attr.string(
            doc = "The module name to use in generation.",
            default = "",
        ),
        "reset": attr.string(
            doc = "The reset signal to use in generation.",
            default = "",
        ),
        "top": attr.string(
            doc = "The top entry function within the dependency module.",
            mandatory = True,
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
        "unopt_ir_file": "%{name}.unopt.ir",
        "opt_ir_file": "%{name}.opt.ir",
    },
)
