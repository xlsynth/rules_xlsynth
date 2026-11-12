# SPDX-License-Identifier: Apache-2.0

"""Bazel test rule for SystemVerilog benches running under Icarus Verilog."""

load("@bazel_skylib//lib:shell.bzl", "shell")

def _sv_sim_test_impl(ctx):
    if not ctx.files.srcs:
        fail("srcs must supply at least one SystemVerilog or Verilog source")
    if not ctx.attr.top:
        fail("top must name the testbench module")

    iverilog = ctx.executable.iverilog
    vvp = ctx.executable.vvp
    compile_args = ["./" + iverilog.short_path, "-g2012", "-s", ctx.attr.top] + ctx.attr.iverilog_args
    compile_command = " ".join([shell.quote(arg) for arg in compile_args])
    source_args = " ".join([shell.quote(file.short_path) for file in ctx.files.srcs])

    # Bazel starts tests in the workspace runfiles directory. External files'
    # short paths are relative to that directory through its parent.
    launcher = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        output = launcher,
        content = "\n".join([
            "#!/bin/bash",
            "set -euo pipefail",
            'export RUNFILES_DIR="${RUNFILES_DIR:-$TEST_SRCDIR}"',
            'export TMPDIR="$TEST_TMPDIR"',
            'simulation="$TEST_TMPDIR/simulation.vvp"',
            compile_command + ' -o "$simulation" ' + source_args,
            "exec " + shell.quote("./" + vvp.short_path) + ' "$simulation" "$@"',
            "",
        ]),
        is_executable = True,
    )

    runfiles = ctx.runfiles(files = ctx.files.srcs + ctx.files.data + [iverilog, vvp])
    runfiles = runfiles.merge_all([
        dep[DefaultInfo].default_runfiles
        for dep in [ctx.attr.iverilog, ctx.attr.vvp] + ctx.attr.data
    ])
    return DefaultInfo(executable = launcher, runfiles = runfiles)

sv_sim_test = rule(
    doc = "Compiles and runs a SystemVerilog testbench with declared Icarus Verilog executables.",
    implementation = _sv_sim_test_impl,
    attrs = {
        "srcs": attr.label_list(
            allow_empty = False,
            allow_files = [".sv", ".v"],
            doc = "Testbench and design sources, including targets that generate SystemVerilog.",
        ),
        "top": attr.string(
            mandatory = True,
            doc = "Name of the testbench module to elaborate.",
        ),
        "iverilog": attr.label(
            executable = True,
            cfg = "target",
            mandatory = True,
            doc = "Icarus Verilog compiler executable target, including its runtime files.",
        ),
        "vvp": attr.label(
            executable = True,
            cfg = "target",
            mandatory = True,
            doc = "Icarus Verilog simulator executable target, including its runtime files.",
        ),
        "data": attr.label_list(
            allow_files = True,
            doc = "Additional test runfiles, such as HDL include files and memory initialization data.",
        ),
        "iverilog_args": attr.string_list(
            doc = "Additional compiler arguments, such as defines and include paths relative to the test runfiles working directory.",
        ),
    },
    test = True,
)
