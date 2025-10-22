# SPDX-License-Identifier: Apache-2.0

load(":env_helpers.bzl", "python_runner_source")
load(":helpers.bzl", "write_executable_shell_script")
load(":ir_provider.bzl", "IrInfo")

def _ir_prove_equiv_test_impl(ctx):
    lhs_files = ctx.files.lhs
    rhs_files = ctx.files.rhs
    if not lhs_files:
        fail("lhs attribute must produce a file")
    if not rhs_files:
        fail("rhs attribute must produce a file")
    lhs_file = list(lhs_files)[0]
    rhs_file = list(rhs_files)[0]

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source())
    extra_flags = ""
    if len(ctx.attr.xlsynth_flags) > 0:
        extra_flags = " " + " ".join(ctx.attr.xlsynth_flags)
    cmd = "/usr/bin/env python3 {} driver ir-equiv --top={} {} {}".format(
        runner.short_path,
        ctx.attr.top,
        lhs_file.short_path,
        rhs_file.short_path,
    ) + extra_flags
    run_script = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + ".sh",
        cmd = cmd,
    )
    return DefaultInfo(
        files = depset(direct = [run_script]),
        runfiles = ctx.runfiles(
            files = [lhs_file, rhs_file, runner],
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
            mandatory = True,
            doc = "The top entity to check in the IR files.",
        ),
        "xlsynth_flags": attr.string_list(
            doc = "Flags passed directly down to the xlsynth driver",
            default = [],
        ),
    },
    executable = True,
    test = True,
)
