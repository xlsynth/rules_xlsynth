# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":helpers.bzl", "get_srcs_from_deps")

def _dslx_to_pipeline_eco_impl(ctx):
    srcs = get_srcs_from_deps(ctx)

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

    if not ctx.file.baseline_unopt_ir:
        fail("Please specify the 'baseline_unopt_ir' file to use")
    srcs.append(ctx.file.baseline_unopt_ir)

    if ctx.attr.reset:
        flags_str += " --reset={}".format(ctx.attr.reset)

    extra_flags = ""
    if len(ctx.attr.xlsynth_flags) > 0:
        extra_flags = " " + " ".join(ctx.attr.xlsynth_flags)

    output_sv_file = ctx.outputs.sv_file
    output_unopt_ir_file = ctx.outputs.unopt_ir_file
    output_opt_ir_file = ctx.outputs.opt_ir_file
    baseline_unopt_ir_file = ctx.file.baseline_unopt_ir
    output_baseline_verilog_file = ctx.outputs.baseline_verilog_file
    output_eco_edit_file = ctx.outputs.eco_edit_file

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source())

    ctx.actions.run_shell(
        inputs = srcs,
        tools = [runner],
        outputs = [output_sv_file, output_unopt_ir_file, output_opt_ir_file, output_baseline_verilog_file, output_eco_edit_file],
        command = "\"$1\" driver dslx2pipeline-eco --dslx_input_file=\"$2\" --dslx_top=\"$3\" --baseline_unopt_ir=\"$4\" --output_unopt_ir=\"$5\" --output_opt_ir=\"$6\" --output_baseline_verilog_path=\"$7\" --edits_debug_out=\"$9\"" + flags_str + extra_flags + " > \"$8\"",
        arguments = [
            runner.path,
            srcs[0].path,
            top_entry,
            baseline_unopt_ir_file.path,
            output_unopt_ir_file.path,
            output_opt_ir_file.path,
            output_baseline_verilog_file.path,
            output_sv_file.path,
            output_eco_edit_file.path,
        ],
        use_default_shell_env = True,
    )

    return DefaultInfo(
        files = depset(direct = [output_sv_file]),
    )

DslxToPipelineEcoAttrs = {
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
    "baseline_unopt_ir": attr.label(
        doc = "The unoptimized IR file of the ECO baseline.",
        mandatory = True,
        allow_single_file = [".ir"],
    ),
    "xlsynth_flags": attr.string_list(
        doc = "Flags passed directly down to the xlsynth driver",
        default = [],
    ),
}

# Keep the public rule signature stable
DslxToPipelineEcoOutputs = {
    "sv_file": "%{name}.sv",
    "unopt_ir_file": "%{name}.unopt.ir",
    "opt_ir_file": "%{name}.opt.ir",
    "baseline_verilog_file": "%{name}.baseline.sv",
    "eco_edit_file": "%{name}.edits.txt",
}

dslx_to_pipeline_eco = rule(
    doc = "Convert a DSLX file to SystemVerilog type definitions",
    implementation = _dslx_to_pipeline_eco_impl,
    attrs = DslxToPipelineEcoAttrs,
    outputs = DslxToPipelineEcoOutputs,
)
