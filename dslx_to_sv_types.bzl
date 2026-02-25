# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":helpers.bzl", "get_srcs_from_deps")

_SV_ENUM_CASE_NAMING_POLICIES = [
    "unqualified",
    "enum_qualified",
]

def _dslx_to_sv_types_impl(ctx):
    srcs = get_srcs_from_deps(ctx)

    output_sv_file = ctx.outputs.sv_file

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source())

    ctx.actions.run_shell(
        inputs = srcs,
        tools = [runner],
        outputs = [output_sv_file],
        command = "\"$1\" driver dslx2sv-types --dslx_input_file=\"$2\" \"$3\" > \"$4\"",
        arguments = [
            runner.path,
            srcs[0].path,
            "--sv_enum_case_naming_policy=" + ctx.attr.sv_enum_case_naming_policy,
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
        "sv_enum_case_naming_policy": attr.string(
            doc = "Enum case naming policy passed to xlsynth-driver (`unqualified` or `enum_qualified`).",
            mandatory = True,
            values = _SV_ENUM_CASE_NAMING_POLICIES,
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
    },
)
