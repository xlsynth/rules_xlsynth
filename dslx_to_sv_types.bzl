# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")

def _dslx_to_sv_types_impl(ctx):
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir = env.get("XLSYNTH_TOOLS")
    if not xlsynth_tool_dir:
        fail("Please set XLSYNTH_TOOLS environment variable")
    xlsynth_driver_dir = env.get("XLSYNTH_DRIVER_DIR")
    if not xlsynth_driver_dir:
        fail("Please set XLSYNTH_DRIVER_DIR environment variable")

    # Ensure the interpreter binary exists
    xlsynth_driver_file = xlsynth_driver_dir + "/xlsynth-driver"

    # Get DAG entries from DslxInfo
    dag_entries = []
    for dep in ctx.attr.deps:
        dag_entries.extend(dep[DslxInfo].dag.to_list())

    srcs = []
    for entry in dag_entries:
        srcs += [src for src in list(entry.srcs)]

    srcs = list(reversed(srcs))

    flags_str = '--dslx_stdlib_path=' + xlsynth_tool_dir + '/xls/dslx/stdlib'

    additional_dslx_paths = env.get("XLSYNTH_DSLX_PATH")
    if additional_dslx_paths:
        flags_str += ' --dslx_path=' + additional_dslx_paths

    # Define the output .sv file
    output_sv_file = ctx.outputs.sv_file
    output_sv_path = output_sv_file.path

    cmd = "{} dslx2sv-types {} {} > {}".format(
        xlsynth_driver_file,
        flags_str,
        ' '.join([src.path for src in srcs]),
        output_sv_path,
    )

    ctx.actions.run(
        inputs = srcs,
        outputs = [output_sv_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
        use_default_shell_env = True,
    )

    return DefaultInfo(
        files = depset(direct = [output_sv_file]),
    )

dslx_to_sv_types = rule(
    doc = "Convert a DSLX file to SystemVerilog type definitions",
    implementation = _dslx_to_sv_types_impl,
    attrs = {
        "deps": attr.label_list(
            doc = "The list of DSLX libraries to be tested.",
            providers = [DslxInfo],
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
    },
)

