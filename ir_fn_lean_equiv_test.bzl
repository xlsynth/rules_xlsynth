# SPDX-License-Identifier: Apache-2.0
"""Bazel test for a Lean proof of equivalence between two XLS IR functions."""

load(":env_helpers.bzl", "python_runner_source")
load(":ir_provider.bzl", "IrInfo")
load(":lean_equiv_common.bzl", "lean_proof_test")
load(":xls_toolchain.bzl", "XlsArtifactBundleInfo", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "require_lean_toolchain")

def _ir_input(dep):
    if IrInfo in dep:
        return dep[IrInfo].opt_ir_file
    files = dep[DefaultInfo].files.to_list()
    if len(files) != 1 or files[0].extension != "ir":
        fail("{} must provide IrInfo or one .ir file".format(dep.label))
    return files[0]

def _prepare_target(ctx, toolchain, toolchain_file):
    lhs = _ir_input(ctx.attr.lhs)
    rhs = _ir_input(ctx.attr.rhs)
    runner = ctx.actions.declare_file(ctx.label.name + "_driver.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    target = ctx.actions.declare_directory(ctx.label.name + ".lean_target")
    args = [
        "driver",
        "--driver_path",
        toolchain.driver_path,
        "--toolchain",
        toolchain_file.path,
    ]
    if toolchain.runtime_library_path:
        args.extend(["--runtime_library_path", toolchain.runtime_library_path])
    args.extend([
        "ir-fn-lean-prepare",
        "--lhs",
        lhs.path,
        "--rhs",
        rhs.path,
        "--output-dir",
        target.path,
    ])
    if ctx.attr.lhs_top:
        args.extend(["--lhs-top", ctx.attr.lhs_top])
    if ctx.attr.rhs_top:
        args.extend(["--rhs-top", ctx.attr.rhs_top])
    ctx.actions.run(
        executable = runner,
        inputs = [lhs, rhs, toolchain_file] + get_driver_artifact_inputs(toolchain),
        outputs = [target],
        arguments = args,
        progress_message = "Generating Lean function equivalence target for {}".format(ctx.label),
        mnemonic = "XlsynthIrFnLeanPrepare",
    )
    return target

def _ir_fn_lean_equiv_test_impl(ctx):
    toolchain = require_lean_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "ir_fn_lean_equiv", toolchain = toolchain)
    target = _prepare_target(ctx, toolchain, toolchain_file)
    return lean_proof_test(ctx, toolchain, toolchain_file, target, {
        "check_command": "ir-fn-lean-check",
        "allow_native_checks": ctx.attr.allow_native_checks,
        "proof_theorem": ctx.attr.proof_theorem,
    })

ir_fn_lean_equiv_test = rule(
    doc = "Checks and audits a Lean proof of pointwise equivalence for two pure XLS IR functions.",
    implementation = _ir_fn_lean_equiv_test_impl,
    attrs = {
        "lhs": attr.label(allow_files = [".ir"], mandatory = True, doc = "Left IR file or DSLX-to-IR target (optimized IR)."),
        "rhs": attr.label(allow_files = [".ir"], mandatory = True, doc = "Right IR file or DSLX-to-IR target (optimized IR)."),
        "lhs_top": attr.string(doc = "Override the left package's top or sole function."),
        "rhs_top": attr.string(doc = "Override the right package's top or sole function."),
        "proof": attr.label(allow_single_file = [".lean"], mandatory = True, doc = "Lean module containing the selected equivalence theorem."),
        "proof_theorem": attr.string(mandatory = True, doc = "Fully qualified name of the theorem proving Target.Equivalent."),
        "proof_srcs": attr.label_list(allow_files = [".lean"], doc = "Additional Lean modules available for the proof to import."),
        "allow_native_checks": attr.bool(default = True, doc = "Allow replaying native Boolean checks. Set to False to require only the three standard Lean axioms."),
        "xls_bundle": attr.label(providers = [XlsArtifactBundleInfo], doc = "Optional XLS bundle override for the proof driver and Lean distribution."),
        "_test_runner": attr.label(default = Label("//:lean_equiv_runner.py"), allow_single_file = True),
    },
    test = True,
    toolchains = ["//:toolchain_type"],
)
