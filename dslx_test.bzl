# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_srcs_from_deps", "get_srcs_from_lib", "write_executable_shell_script")


def _dslx_test_impl(ctx):
    """
    Implements a test rule that runs a DSLX interpreter on the given DSLX library sources.

    Args:
      ctx: The context for this rule.

    Returns:
      A struct representing the result of this rule, including any run actions.
    """
    if ctx.attr.src and ctx.attr.lib:
        fail("Don't provide both src and lib.")
    if not ctx.attr.src and not ctx.attr.lib and len(ctx.attr.deps) != 1:
        fail("Must provide src or lib with zero or more dependencies; alternatively, provide exactly one dependency.")

    srcs_from_deps = get_srcs_from_deps(ctx)
    if ctx.attr.src:
        test_src = [ctx.file.src]
    elif ctx.attr.lib:
        test_src = get_srcs_from_lib(ctx)
    else:
        test_src = []

    if len(test_src) == 1 and test_src[0] in srcs_from_deps:
        fail("Don't provide the test through more than one attribute: src/lib/deps.")

    # The order of the srcs matters. dslx_interpreter_main runs tests from the first file.
    srcs = test_src + srcs_from_deps

    cmd = "/usr/bin/env python3 {} tool dslx_interpreter_main {}".format(
        ctx.file._runner.short_path,
        " ".join([src.short_path for src in srcs]),
    )

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


dslx_test = rule(
    doc = "Test a DSLX module using the interpreter.",
    implementation = _dslx_test_impl,
    attrs = {
        "src": attr.label(
            doc = "The DSLX source module to be tested. Use either src or lib, but not both. If there is only one module, you may instead use deps.",
            allow_single_file = [".x"],
        ),
        "lib": attr.label(
            doc = "The DSLX library to be tested. Use either src or lib, but not both. If there is only one module, you may instead use deps.",
            providers = [DslxInfo],
        ),
        "deps": attr.label_list(
            doc = "The DSLX library dependencies for the test.",
            providers = [DslxInfo],
        ),
        "_runner": attr.label(
            default = Label("//:xlsynth_runner.py"),
            allow_single_file = [".py"],
        ),
    },
    test = True,
)
