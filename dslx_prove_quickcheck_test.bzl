# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "write_executable_shell_script", "get_srcs_from_lib")
load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_toolchain_artifact_inputs", "require_tools_toolchain")


def _dslx_prove_quickcheck_test_impl(ctx):
    lib = ctx.attr.lib[DslxInfo]
    lib_srcs = lib.dag.to_list()[-1].srcs
    if len(lib_srcs) != 1:
        fail("Expected exactly one source file for the library; got: " + str(lib_srcs))
    lib_src = lib_srcs[0]

    srcs = get_srcs_from_lib(ctx)

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = require_tools_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "prove_quickcheck")
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
    cmd_parts.extend(["prove_quickcheck_main", lib_src.short_path])
    cmd = " ".join(["\"{}\"".format(part) for part in cmd_parts])
    if ctx.attr.top:
        cmd += " --test_filter=" + ctx.attr.top

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
    },
    test = True,
    toolchains = ["//:toolchain_type"],
)
