# SPDX-License-Identifier: Apache-2.0

load(":helpers.bzl", "write_executable_shell_script")
load(":ir_provider.bzl", "IrInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "require_driver_toolchain")


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
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = require_driver_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "ir_equiv")
    cmd_parts = [
        "/usr/bin/env",
        "python3",
        runner.short_path,
        "driver",
        "--driver_path",
        toolchain.driver_path,
        "--toolchain",
        toolchain_file.short_path,
    ]
    if toolchain.runtime_library_path:
        cmd_parts.extend(["--runtime_library_path", toolchain.runtime_library_path])
    cmd_parts.extend([
        "ir-equiv",
        "--top={}".format(ctx.attr.top),
        lhs_file.short_path,
        rhs_file.short_path,
    ])
    cmd = " ".join(["\"{}\"".format(part) for part in cmd_parts])
    run_script = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + ".sh",
        cmd = cmd,
    )
    return DefaultInfo(
        files = depset(direct = [run_script]),
        runfiles = ctx.runfiles(
            files = [lhs_file, rhs_file, runner, toolchain_file] + get_driver_artifact_inputs(toolchain),
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
    },
    executable = True,
    test = True,
    toolchains = ["//:toolchain_type"],
)
