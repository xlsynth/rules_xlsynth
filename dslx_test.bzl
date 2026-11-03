# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_dslx_input", "write_executable_shell_script")
load(":env_helpers.bzl", "python_runner_source")
load(
    ":xls_toolchain.bzl",
    "XlsArtifactBundleInfo",
    "declare_xls_toolchain_toml",
    "get_selected_tools_toolchain",
    "get_tool_artifact_inputs",
)


def _dslx_test_impl(ctx):
    """
    Runs the DSLX interpreter on the selected root module.

    Args:
      ctx: The context for this rule.

    Returns:
      A struct representing the result of this rule, including any run actions.
    """
    dslx_input = get_dslx_input(ctx)

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = get_selected_tools_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(
        ctx,
        name = "dslx_test",
        toolchain = toolchain,
        additional_disable_warnings = ctx.attr.disable_warnings,
    )
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
    cmd_parts.append(dslx_input.root.short_path)
    cmd = " ".join(["\"{}\"".format(part) for part in cmd_parts])

    runfiles = ctx.runfiles(dslx_input.srcs + [runner, toolchain_file] + get_tool_artifact_inputs(toolchain, "dslx_interpreter_main"))
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
            doc = "The DSLX source module to be tested. Use either src or lib, but not both; one deps library is also sufficient.",
            allow_single_file = [".x"],
        ),
        "lib": attr.label(
            doc = "The DSLX library whose root is tested. Use either src or lib, but not both; one deps library is also sufficient.",
            providers = [DslxInfo],
        ),
        "deps": attr.label_list(
            doc = "The DSLX library dependencies for the test.",
            providers = [DslxInfo],
        ),
        "disable_warnings": attr.string_list(
            doc = "Additional DSLX warnings to disable for this test, added to the configured toolchain suppressions.",
            default = [],
        ),
        "xls_bundle": attr.label(
            doc = "Optional XLS bundle override.",
            providers = [XlsArtifactBundleInfo],
        ),
    },
    test = True,
    toolchains = ["//:toolchain_type"],
)
