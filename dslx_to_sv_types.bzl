# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":helpers.bzl", "get_srcs_from_deps")

def _dslx_to_sv_types_impl(ctx):
    srcs = get_srcs_from_deps(ctx)

    output_sv_file = ctx.outputs.sv_file

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source())
    extra_flags = ""
    if len(ctx.attr.xlsynth_flags) > 0:
        extra_flags = " " + " ".join(ctx.attr.xlsynth_flags)

    ctx.actions.run_shell(
        inputs = srcs,
        tools = [runner],
        outputs = [output_sv_file],
        command = "\"$1\" driver dslx2sv-types --dslx_input_file=\"$2\"" + extra_flags + " > \"$3\"",
        arguments = [
            runner.path,
            srcs[0].path,
            output_sv_file.path,
        ],
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
        "xlsynth_flags": attr.string_list(
            doc = "Flags passed directly down to the xlsynth driver",
            default = [],
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
    },
)
