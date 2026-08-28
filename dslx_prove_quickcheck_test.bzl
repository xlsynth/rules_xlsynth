# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//lib:shell.bzl", "shell")
load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "write_executable_shell_script", "get_srcs_from_lib")
load(":env_helpers.bzl", "python_runner_source")
load(
    ":xls_toolchain.bzl",
    "XlsArtifactBundleInfo",
    "declare_xls_toolchain_toml",
    "get_driver_artifact_inputs",
    "get_selected_driver_toolchain",
)


def _dslx_prove_quickcheck_test_impl(ctx):
    lib = ctx.attr.lib[DslxInfo]
    lib_srcs = lib.dag.to_list()[-1].srcs
    if len(lib_srcs) != 1:
        fail("Expected exactly one source file for the library; got: " + str(lib_srcs))
    lib_src = lib_srcs[0]

    srcs = get_srcs_from_lib(ctx)

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = get_selected_driver_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "prove_quickcheck", toolchain = toolchain)
    cmd_parts = [
        "/usr/bin/env",
        "python3",
        runner.short_path,
        "quickcheck",
        "--driver_path",
        toolchain.driver_path,
        "--toolchain",
        toolchain_file.short_path,
        "--dslx_input_file",
        lib_src.short_path,
    ]
    if toolchain.runtime_library_path:
        cmd_parts.extend(["--runtime_library_path", toolchain.runtime_library_path])
    if ctx.attr.top:
        cmd_parts.extend(["--top", ctx.attr.top])
    cmd = " ".join([shell.quote(part) for part in cmd_parts])

    runfiles = ctx.runfiles(srcs + [runner, toolchain_file] + get_driver_artifact_inputs(toolchain, ["typecheck_main"]))
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
    doc = "Prove DSLX quickchecks over their entire input domain using xlsynth-driver and Bitwuzla.",
    implementation = _dslx_prove_quickcheck_test_impl,
    attrs = {
        "lib": attr.label(
            doc = "The DSLX library to be tested.",
            providers = [DslxInfo],
            mandatory = True,
        ),
        "top": attr.string(
            doc = "Full-match regular expression selecting quickcheck function names. If omitted, prove all quickchecks in the library. An empty selection fails.",
        ),
        "xls_bundle": attr.label(
            doc = "Optional XLS bundle override.",
            providers = [XlsArtifactBundleInfo],
        ),
    },
    test = True,
    toolchains = ["//:toolchain_type"],
)
