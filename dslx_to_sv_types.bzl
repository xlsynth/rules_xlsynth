# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_srcs_from_deps")


def _dslx_to_sv_types_impl(ctx):
    srcs = get_srcs_from_deps(ctx)

    output_sv_file = ctx.outputs.sv_file

    ctx.actions.run(
        inputs = srcs + [ctx.file._runner],
        outputs = [output_sv_file],
        executable = "/usr/bin/env",
        arguments = [
            "python3",
            ctx.file._runner.path,
            "driver",
            "dslx2sv-types",
            "--dslx_input_file={}".format(srcs[0].path),
            "--stdout_out", output_sv_file.path,
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
        "_runner": attr.label(
            default = Label("//:xlsynth_runner.py"),
            allow_single_file = [".py"],
        ),
    },
    outputs = {
        "sv_file": "%{name}.sv",
    },
)
