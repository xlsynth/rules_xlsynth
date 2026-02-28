# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":helpers.bzl", "get_srcs_from_deps")
load(":xls_toolchain.bzl", "XlsArtifactBundleInfo", "declare_xls_toolchain_toml", "get_selected_driver_toolchain", "get_toolchain_artifact_inputs")

_SV_ENUM_CASE_NAMING_POLICIES = [
    "unqualified",
    "enum_qualified",
]

def _dslx_to_sv_types_impl(ctx):
    srcs = get_srcs_from_deps(ctx)

    output_sv_file = ctx.outputs.sv_file

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = get_selected_driver_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "dslx_to_sv_types", toolchain = toolchain)
    arguments = [
        "driver",
        "--driver_path",
        toolchain.driver_path,
        "--runtime_library_path",
        toolchain.runtime_library_path,
        "--toolchain",
        toolchain_file.path,
        "--stdout_path",
        output_sv_file.path,
        "dslx2sv-types",
        "--dslx_input_file",
        srcs[0].path,
    ]

    if toolchain.driver_supports_sv_enum_case_naming_policy:
        arguments.append("--sv_enum_case_naming_policy=" + ctx.attr.sv_enum_case_naming_policy)
    else:
        if ctx.attr.sv_enum_case_naming_policy != "unqualified":
            fail("sv_enum_case_naming_policy={} requires @rules_xlsynth//config:driver_supports_sv_enum_case_naming_policy=true".format(ctx.attr.sv_enum_case_naming_policy))

    ctx.actions.run(
        inputs = srcs + [toolchain_file] + get_toolchain_artifact_inputs(toolchain),
        executable = runner,
        outputs = [output_sv_file],
        arguments = arguments,
        use_default_shell_env = False,
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
