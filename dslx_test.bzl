# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_srcs_from_deps", "get_srcs_from_lib", "write_executable_shell_script")
load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_toolchain_artifact_inputs", "require_tools_toolchain")


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

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = require_tools_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "dslx_test")
    cmd_parts = [
        "/usr/bin/env",
        "python3",
        runner.short_path,
        "tool",
        "--toolchain",
        toolchain_file.short_path,
    ]
    if toolchain.runtime_library_path:
        cmd_parts.extend(["--runtime_library_path", toolchain.runtime_library_path])
    cmd_parts.append("dslx_interpreter_main")
    cmd_parts.extend([src.short_path for src in srcs])
    cmd = " ".join(["\"{}\"".format(part) for part in cmd_parts])

    runfiles = ctx.runfiles(srcs + [runner, toolchain_file] + get_toolchain_artifact_inputs(toolchain))
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
    },
    test = True,
    toolchains = ["//:toolchain_type"],
)
