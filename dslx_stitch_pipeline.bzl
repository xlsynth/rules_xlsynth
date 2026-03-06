# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_srcs_from_lib")
load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "XlsArtifactBundleInfo", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "get_selected_driver_toolchain")


def _dslx_stitch_pipeline_impl(ctx):
    lib_info = ctx.attr.lib[DslxInfo]
    lib_dag_list = lib_info.dag.to_list()
    if not lib_dag_list:
        fail("DAG for library {} is empty".format(ctx.attr.lib.label))
    main_srcs = lib_dag_list[-1].srcs
    if len(main_srcs) != 1:
        fail("Expected exactly one source file for the library {}; got: {}".format(ctx.attr.lib.label, [s.path for s in main_srcs]))
    main_src = main_srcs[0]

    srcs = get_srcs_from_lib(ctx)

    passthrough = [
        "--use_system_verilog={}".format(str(ctx.attr.use_system_verilog).lower()),
    ]
    use_explicit_stages = len(ctx.attr.stages) > 0
    if use_explicit_stages:
        passthrough.append("--stages=" + ",".join(ctx.attr.stages))
        # xlsynth-driver v0.33.0+ requires output_module_name when --stages is used
        # and rejects --dslx_top in that mode. Reuse the existing `top` attr as the
        # wrapper module name to preserve rule callsites.
        passthrough.append("--output_module_name=" + ctx.attr.top)

    string_flags = [
        "input_valid_signal",
        "output_valid_signal",
        "reset",
    ]
    for flag in string_flags:
        value = getattr(ctx.attr, flag)
        if value:
            passthrough.append("--{}={}".format(flag, value))

    bool_flags = [
        "reset_active_low",
        "flop_inputs",
        "flop_outputs",
    ]
    for flag in bool_flags:
        value = getattr(ctx.attr, flag)
        passthrough.append("--{}={}".format(flag, str(value).lower()))

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = get_selected_driver_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "dslx_stitch_pipeline", toolchain = toolchain)

    dslx_top_arg = ""
    if not use_explicit_stages:
        dslx_top_arg = ctx.attr.top

    arguments = [
        "driver",
        "--driver_path",
        toolchain.driver_path,
        "--runtime_library_path",
        toolchain.runtime_library_path,
        "--toolchain",
        toolchain_file.path,
        "--stdout_path",
        ctx.outputs.sv_file.path,
        "dslx-stitch-pipeline",
        "--dslx_input_file=" + main_src.path,
    ]
    if dslx_top_arg:
        arguments.append("--dslx_top=" + dslx_top_arg)
    arguments.extend(passthrough)

    ctx.actions.run(
        inputs = srcs + [toolchain_file] + get_driver_artifact_inputs(toolchain),
        executable = runner,
        outputs = [ctx.outputs.sv_file],
        arguments = arguments,
        use_default_shell_env = False,
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
            doc = "Prefix for implicit stage discovery (e.g. foo for foo_cycleN); when `stages` is set, used as the output wrapper module name.",
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
        "xls_bundle": attr.label(
            doc = "Optional override bundle repo label, for example @legacy_xls//:bundle.",
            providers = [XlsArtifactBundleInfo],
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
    },
    toolchains = ["//:toolchain_type"],
)
