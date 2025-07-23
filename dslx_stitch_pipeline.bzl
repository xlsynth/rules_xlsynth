# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_driver_path", "get_srcs_from_lib", "write_config_toml")


def _dslx_stitch_pipeline_impl(ctx):
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)
    lib_info = ctx.attr.lib[DslxInfo]
    lib_dag_list = lib_info.dag.to_list()
    if not lib_dag_list:
        fail("DAG for library {} is empty".format(ctx.attr.lib.label))
    main_srcs = lib_dag_list[-1].srcs
    if len(main_srcs) != 1:
        fail("Expected exactly one source file for the library {}; got: {}".format(ctx.attr.lib.label, [s.path for s in main_srcs]))
    main_src = main_srcs[0]

    srcs = get_srcs_from_lib(ctx)
    config_file = write_config_toml(ctx, xlsynth_tool_dir)

    flags_str = " --use_system_verilog={}".format(
        str(ctx.attr.use_system_verilog).lower()
    )
    if ctx.attr.stages:
        flags_str += " --stages=" + ",".join(ctx.attr.stages)

    # String-based flags that should be forwarded verbatim when specified.
    string_flags = [
        "input_valid_signal",
        "output_valid_signal",
        "reset",
    ]
    for flag in string_flags:
        value = getattr(ctx.attr, flag)
        if value:
            flags_str += " --{}={}".format(flag, value)

    # Boolean flags that are always forwarded to document the chosen default.
    bool_flags = [
        "reset_active_low",
        "flop_inputs",
        "flop_outputs",
    ]
    for flag in bool_flags:
        value = getattr(ctx.attr, flag)
        flags_str += " --{}={}".format(flag, str(value).lower())

    cmd = "{driver} --toolchain={toolchain} dslx-stitch-pipeline --dslx_input_file={src} --dslx_top={top}{flags} > {output}".format(
        driver = xlsynth_driver_file,
        toolchain = config_file.path,
        src = main_src.path,
        top = ctx.attr.top,
        flags = flags_str,
        output = ctx.outputs.sv_file.path,
    )

    ctx.actions.run(
        inputs = srcs + [config_file],
        outputs = [ctx.outputs.sv_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
        use_default_shell_env = True,
    )

    return DefaultInfo(
        files = depset(direct = [ctx.outputs.sv_file]),
    )


dslx_stitch_pipeline = rule(
    doc = "Stitch pipeline stage functions into a wrapper module",
    implementation = _dslx_stitch_pipeline_impl,
    attrs = {
        "lib": attr.label(
            doc = "The DSLX library containing the pipeline stage functions.",
            providers = [DslxInfo],
            mandatory = True,
        ),
        "top": attr.string(
            doc = "Prefix for the pipeline stage functions (e.g. foo for foo_cycleN).",
            mandatory = True,
        ),
        "stages": attr.string_list(
            doc = "Explicit stage function names in order; overrides automatic discovery.",
        ),
        "use_system_verilog": attr.bool(
            doc = "Emit SystemVerilog when true, plain Verilog when false.",
            default = True,
        ),
        "input_valid_signal": attr.string(
            doc = "The pipeline load enable signal to use for input data.",
        ),
        "output_valid_signal": attr.string(
            doc = "The pipeline load enable signal for output data.",
        ),
        "reset": attr.string(
            doc = "The reset signal to use in generation.",
        ),
        "reset_active_low": attr.bool(
            doc = "Whether the reset signal is active low (true) or active high (false).",
            default = False,
        ),
        "flop_inputs": attr.bool(
            doc = "Whether to insert flops on inputs (true) or not (false).",
            default = True,
        ),
        "flop_outputs": attr.bool(
            doc = "Whether to insert flops on outputs (true) or not (false).",
            default = True,
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
    },
)
