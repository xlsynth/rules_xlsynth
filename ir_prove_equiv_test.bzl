# SPDX-License-Identifier: Apache-2.0

load(":helpers.bzl", "get_driver_path", "write_config_toml", "write_executable_shell_script")
load(":ir_provider.bzl", "IrInfo")

def _ir_prove_equiv_test_impl(ctx):
    """
    Implements a test rule that proves two IR files are equivalent.

    Args:
      ctx: The context for this rule.

    Returns:
      A struct representing the result of this rule, including any run actions.
    """
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)
    config_file = write_config_toml(ctx, xlsynth_tool_dir)

    # Get the two IR file inputs
    lhs_files = ctx.files.lhs
    rhs_files = ctx.files.rhs
    if not lhs_files:
        fail("lhs attribute must produce a file")
    if not rhs_files:
        fail("rhs attribute must produce a file")
    lhs_file = list(lhs_files)[0]
    rhs_file = list(rhs_files)[0]

    cmd = "{driver} --toolchain=\"{toolchain_config}\" ir-equiv --top={top} {lhs} {rhs}".format(
        driver = xlsynth_driver_file,
        toolchain_config = config_file.short_path,
        lhs = lhs_file.short_path,
        rhs = rhs_file.short_path,
        top = ctx.attr.top,
    )
    run_script = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + ".sh",
        cmd = cmd,
    )
    return DefaultInfo(
        files = depset(direct = [run_script]),
        runfiles = ctx.runfiles(
            files = [config_file, lhs_file, rhs_file],
        ),
        executable = run_script,
    )

ir_prove_equiv_test = rule(
    doc = "Test rule that proves two IR files are equivalent by running ir-equiv.",
    implementation = _ir_prove_equiv_test_impl,
    attrs = {
        "lhs": attr.label(
            allow_single_file = True,
            mandatory = True,
            doc = "The left hand side IR file (.ir).",
        ),
        "rhs": attr.label(
            allow_single_file = True,
            mandatory = True,
            doc = "The right hand side IR file (.ir).",
        ),
        "top": attr.string(
            # Right now the auto-discovery of the top entity is sub-par, so we'll make it mandatory
            # to specify for the moment.
            mandatory = True,
            doc = "The top entity to check in the IR files.",
        ),
    },
    executable = True,
    test = True,
)
