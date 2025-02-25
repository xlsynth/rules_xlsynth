# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "write_executable_shell_script", "get_driver_path", "get_srcs_from_deps")

def _dslx_prove_quickcheck_test_impl(ctx):
    """
    Implements a test rule that proves a quickcheck holds for its entire input domain.

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
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)
    prove_quickcheck_main_file = xlsynth_tool_dir + "/prove_quickcheck_main"

    lib = ctx.attr.lib[DslxInfo]
    lib_srcs = lib.dag.to_list()[0].srcs
    if len(lib_srcs) != 1:
        fail("Expected exactly one source file for the library; got: " + str(lib_srcs))
    lib_src = lib_srcs[0]

    srcs = get_srcs_from_deps(ctx) + [lib_src]

    flags_str = '--alsologtostderr --dslx_stdlib_path=' + xlsynth_tool_dir + '/xls/dslx/stdlib'

    additional_dslx_paths = env.get("XLSYNTH_DSLX_PATH")
    if additional_dslx_paths:
        flags_str += ' --dslx_path=' + additional_dslx_paths

    cmd = prove_quickcheck_main_file + ' ' + flags_str + ' ' + lib_src.path

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

dslx_prove_quickcheck_test = rule(
    doc = "Prove a DSLX quickcheck holds for its entire input domain.",
    implementation = _dslx_prove_quickcheck_test_impl,
    attrs = {
        "lib": attr.label(
            doc = "The DSLX library to be tested.",
            providers = [DslxInfo],
        ),
        "deps": attr.label_list(
            doc = "The list of DSLX libraries to be tested.",
            providers = [DslxInfo],
        ),
        "top": attr.string(
            doc = "The quickcheck function to be tested.",
        ),
    },
    test = True,
)
