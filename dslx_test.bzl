# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_driver_path", "get_srcs_from_deps", "write_executable_shell_script")

def _dslx_test_impl(ctx):
    """
    Implements a test rule that runs a DSLX interpreter on the given DSLX library sources.

    Args:
      ctx: The context for this rule.

    Returns:
      A struct representing the result of this rule, including any run actions.
    """
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir = env.get("XLSYNTH_TOOLS")
    if not xlsynth_tool_dir:
        fail("Please set XLSYNTH_TOOLS environment variable")

    # Ensure the interpreter binary exists
    xlsynth_tool_dir, _xlsynth_driver_file = get_driver_path(ctx)
    dslx_interpreter_file = xlsynth_tool_dir + "/dslx_interpreter_main"

    srcs = get_srcs_from_deps(ctx)

    flags_str = "--compare=jit --alsologtostderr --dslx_stdlib_path=" + xlsynth_tool_dir + "/xls/dslx/stdlib"

    additional_dslx_paths = env.get("XLSYNTH_DSLX_PATH")
    if additional_dslx_paths:
        flags_str += " --dslx_path=" + additional_dslx_paths

    enable_warnings = env.get("XLSYNTH_DSLX_ENABLE_WARNINGS")
    if enable_warnings:
        flags_str += " --enable_warnings=" + enable_warnings

    disable_warnings = env.get("XLSYNTH_DSLX_DISABLE_WARNINGS")
    if disable_warnings:
        flags_str += " --disable_warnings=" + disable_warnings

    cmd = dslx_interpreter_file + " " + flags_str + " " + " ".join([src.path for src in srcs])

    print("cmd: " + cmd)

    runfiles = ctx.runfiles(srcs)
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
        "deps": attr.label_list(
            doc = "The list of DSLX libraries to be tested.",
            providers = [DslxInfo],
        ),
    },
    test = True,
)
