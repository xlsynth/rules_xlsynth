# SPDX-License-Identifier: Apache-2.0

"""Native BX simulation and proof rules."""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:shell.bzl", "shell")
load(":bx_to_ir.bzl", "BX_SOURCE_ATTRS", "get_bx_source_input")
load(":bx_toolchain.bzl", "bx_runtime_env", "require_bx_toolchain")
load(":helpers.bzl", "write_executable_shell_script")
load(
    ":xls_toolchain.bzl",
    "declare_xls_toolchain_toml",
    "get_driver_artifact_inputs",
    "get_selected_driver_toolchain",
)

_TIME_LIMIT_MS_ATTR = attr.int(
    doc = "Positive time limit per solver check in milliseconds. Zero uses the driver's unlimited default.",
)

def _run_bx_test(ctx, command, arguments):
    toolchain = get_selected_driver_toolchain(ctx)
    require_bx_toolchain(toolchain, command)
    source = get_bx_source_input(ctx, toolchain, runfiles = True)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = command, toolchain = toolchain, dslx_path = source.dslx_path)

    library_path = '"$PWD/"' + shell.quote(paths.dirname(toolchain.libxls.short_path) or ".")
    env_exports = {
        name: value + '"${' + name + ":+:$" + name + '}"'
        for name, value in bx_runtime_env(library_path).items()
    }
    command_line = [
        "./" + toolchain.driver.short_path,
        "--toolchain=" + toolchain_file.short_path,
        command,
    ] + source.arguments + arguments

    # Coverage can start the test outside the runfiles directory. The driver's
    # implicit XLS runfiles search would precede the declared import roots.
    script = [
        'if [[ -n "${TEST_SRCDIR:-}" ]]; then',
        '    cd "$TEST_SRCDIR${TEST_WORKSPACE:+/$TEST_WORKSPACE}"',
        "fi",
        "unset RUNFILES_DIR RUNFILES_MANIFEST_FILE",
    ]
    script.extend(["export " + name + "=" + value for name, value in env_exports.items()])
    script.append("exec " + " ".join([shell.quote(arg) for arg in command_line]))
    executable = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + ".sh",
        cmd = "\n".join(script) + "\n",
    )
    return DefaultInfo(
        executable = executable,
        runfiles = ctx.runfiles(files = source.inputs + [toolchain_file] + get_driver_artifact_inputs(toolchain)),
    )

def _bx_test_impl(ctx):
    arguments = [
        "--quickcheck-trials={}".format(ctx.attr.quickcheck_trials),
        "--invariant-cycles={}".format(ctx.attr.invariant_cycles),
        "--seed=" + ctx.attr.seed,
    ]
    if ctx.attr.cross_check_vastly:
        arguments.append("--cross-check-vastly")
    return _run_bx_test(ctx, "bx-test", arguments)

def _time_limit_args(ctx):
    limit = ctx.attr.time_limit_ms
    if limit < 0:
        fail("time_limit_ms must be nonnegative", attr = "time_limit_ms")
    return ["--time-limit-ms={}".format(limit)] if limit else []

def _bx_prove_quickcheck_test_impl(ctx):
    return _run_bx_test(ctx, "bx-prove-quickcheck", ["--solver=bitwuzla"] + _time_limit_args(ctx))

def _bx_prove_invariant_test_impl(ctx):
    arguments = [
        "--mode=" + ctx.attr.mode,
        "--max-depth={}".format(ctx.attr.max_depth),
    ]
    return _run_bx_test(ctx, "bx-prove-invariant", arguments + _time_limit_args(ctx))

bx_test = rule(
    doc = "Run BX unit tests and sample clocked QuickChecks and invariants in the root module.",
    implementation = _bx_test_impl,
    attrs = dict(
        BX_SOURCE_ATTRS,
        quickcheck_trials = attr.int(
            default = 100,
            doc = "Positive number of concrete trials per QuickCheck or invariant.",
        ),
        invariant_cycles = attr.int(
            default = 16,
            doc = "Positive number of sampled cycles per invariant trial.",
        ),
        seed = attr.string(
            default = "0",
            doc = "Unsigned 64-bit random seed as a decimal string.",
        ),
        cross_check_vastly = attr.bool(
            doc = "Compare QuickCheck and invariant trials against generated RTL using Vastly.",
        ),
    ),
    test = True,
    toolchains = ["//:toolchain_type"],
)

bx_prove_quickcheck_test = rule(
    doc = "Prove the root module's BX QuickChecks over their bounded tick schedules using Bitwuzla.",
    implementation = _bx_prove_quickcheck_test_impl,
    attrs = dict(BX_SOURCE_ATTRS, time_limit_ms = _TIME_LIMIT_MS_ATTR),
    test = True,
    toolchains = ["//:toolchain_type"],
)

bx_prove_invariant_test = rule(
    doc = "Check the root module's BX invariants and lemmas using Bitwuzla.",
    implementation = _bx_prove_invariant_test_impl,
    attrs = dict(
        BX_SOURCE_ATTRS,
        mode = attr.string(
            default = "induction",
            doc = "Use k-induction or bounded model checking (bmc).",
            values = ["induction", "bmc"],
        ),
        max_depth = attr.int(
            default = 16,
            doc = "Positive maximum induction depth or number of cycles checked in BMC mode.",
        ),
        time_limit_ms = _TIME_LIMIT_MS_ATTR,
    ),
    test = True,
    toolchains = ["//:toolchain_type"],
)
