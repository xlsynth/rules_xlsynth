# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "write_executable_shell_script", "get_srcs_from_lib")


def _dslx_prove_quickcheck_test_impl(ctx):
    lib = ctx.attr.lib[DslxInfo]
    lib_srcs = lib.dag.to_list()[-1].srcs
    if len(lib_srcs) != 1:
        fail("Expected exactly one source file for the library; got: " + str(lib_srcs))
    lib_src = lib_srcs[0]

    srcs = get_srcs_from_lib(ctx)

    cmd = "/usr/bin/env python3 {} tool prove_quickcheck_main {}".format(
        ctx.file._runner.short_path,
        lib_src.short_path,
    )
    if ctx.attr.top:
        cmd += " --test_filter=" + ctx.attr.top

    runfiles = ctx.runfiles(srcs + [ctx.file._runner])
    executable_file = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + ".sh",
        cmd = cmd,
    )
    return DefaultInfo(
        runfiles = runfiles,
        files = depset(direct = [executable_file]),
        executable = executable_file,
    )


dslx_prove_quickcheck_test = rule(
    doc = "Prove a DSLX quickcheck holds for its entire input domain.",
    implementation = _dslx_prove_quickcheck_test_impl,
    attrs = {
        "lib": attr.label(
            doc = "The DSLX library to be tested.",
            providers = [DslxInfo],
            mandatory = True,
        ),
        "top": attr.string(
            doc = "The quickcheck function to be tested. If none is provided, all quickcheck functions in the library will be tested.",
        ),
        "_runner": attr.label(
            default = Label("//:xlsynth_runner.py"),
            allow_single_file = [".py"],
        ),
    },
    test = True,
)
