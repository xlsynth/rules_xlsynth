# SPDX-License-Identifier: Apache-2.0

"""Executable package checks and analysis checks for DSLX conversion."""

load("@bazel_skylib//lib:shell.bzl", "shell")
load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//:env_helpers.bzl", "python_runner_source")
load("//:helpers.bzl", "write_executable_shell_script")
load("//:ir_provider.bzl", "IrInfo")
load("//:xls_toolchain.bzl", "XlsArtifactBundleInfo", "declare_xls_toolchain_toml", "get_selected_tools_toolchain", "get_tool_artifact_inputs")

def _conversion_test_impl(ctx):
    ir = ctx.attr.ir[IrInfo]
    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(runner, python_runner_source())
    toolchain = get_selected_tools_toolchain(ctx)
    config = declare_xls_toolchain_toml(ctx, name = "validate", toolchain = toolchain)
    args = [
        "python3",
        ctx.file._checker.short_path,
        "--runner",
        runner.short_path,
        "--toolchain",
        config.short_path,
        "--runtime-library-path",
        toolchain.runtime_library_path,
        "--raw",
        ir.ir_file.short_path,
        "--optimized",
        ir.opt_ir_file.short_path,
        "--fixture",
        ctx.attr.fixture,
    ]
    executable = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + ".sh",
        cmd = " ".join([shell.quote(arg) for arg in args]),
    )
    return DefaultInfo(
        executable = executable,
        runfiles = ctx.runfiles(
            [ctx.file._checker, runner, config, ir.ir_file, ir.opt_ir_file] +
            get_tool_artifact_inputs(toolchain, "opt_main"),
        ),
    )

conversion_test = rule(
    implementation = _conversion_test_impl,
    attrs = {
        "ir": attr.label(mandatory = True, providers = [IrInfo]),
        "fixture": attr.string(mandatory = True),
        "_checker": attr.label(default = "//dslx_to_ir_tests:check_conversion.py", allow_single_file = True),
    },
    test = True,
    toolchains = ["//:toolchain_type"],
)

def _config_path_fragment(file):
    # The tested target has an extra_toolchains transition, so its output-root
    # configuration hash need not equal the analysis test's own hash.
    path = file.short_path
    return path[3:] if path.startswith("../") else path

def _conversion_analysis_test_impl(ctx):
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    bundle = ctx.attr.expected_bundle[XlsArtifactBundleInfo]
    actions = analysistest.target_actions(env)
    converters = [a for a in actions if "ir_converter_main" in (a.argv or [])]
    optimizers = [a for a in actions if "opt_main" in (a.argv or [])]
    asserts.equals(env, 1, len(converters))
    asserts.equals(env, 1, len(optimizers))
    asserts.equals(env, ctx.attr.target_name + ".ir", target[IrInfo].ir_file.basename)
    asserts.equals(env, ctx.attr.target_name + ".opt.ir", target[IrInfo].opt_ir_file.basename)
    asserts.equals(env, sorted([target[IrInfo].ir_file.path, target[IrInfo].opt_ir_file.path]), sorted([f.path for f in target[DefaultInfo].files.to_list()]))
    if len(converters) == 1 and len(optimizers) == 1:
        converter, optimizer = converters[0], optimizers[0]
        asserts.equals(env, [target[IrInfo].ir_file], converter.outputs.to_list())
        asserts.equals(env, [target[IrInfo].opt_ir_file], optimizer.outputs.to_list())
        asserts.true(env, target[IrInfo].ir_file in optimizer.inputs.to_list())
        asserts.true(env, target[IrInfo].ir_file.path in optimizer.argv)
        asserts.true(env, "--top" not in optimizer.argv)
        asserts.equals(env, [], [arg for arg in optimizer.argv if arg.startswith("--top=")])
        for action, tool_name in [(converter, "ir_converter_main"), (optimizer, "opt_main")]:
            inputs = action.inputs.to_list()
            input_paths = [f.short_path for f in inputs]
            expected_tool = [f for f in bundle.artifact_inputs if f.basename == tool_name]
            asserts.equals(env, 1, len(expected_tool))
            asserts.equals(env, [f.short_path for f in expected_tool], [f.short_path for f in inputs if f.basename == tool_name])
            asserts.true(env, bundle.driver.short_path not in input_paths)
            asserts.equals(env, [], [f.path for f in inputs if "xlsynth-driver" in f.basename])
            asserts.true(env, bundle.dslx_stdlib.short_path in input_paths)
            for runtime in bundle.runtime_files:
                asserts.true(env, runtime.short_path in input_paths)
            configs = [a for a in actions if any([f in inputs and f.extension == "toml" for f in a.outputs.to_list()])]
            asserts.equals(env, 1, len(configs))
            if configs:
                tool_root = "/".join(_config_path_fragment(bundle.tools_root).split("/")[:-1])
                asserts.true(env, tool_root in configs[0].content)
                asserts.true(env, _config_path_fragment(bundle.dslx_stdlib) in configs[0].content)
        asserts.true(env, ctx.file.source in converter.inputs.to_list())
        asserts.true(env, ctx.file.source.path in converter.argv)
        asserts.true(env, ctx.file.source not in optimizer.inputs.to_list())
    return analysistest.end(env)

_ANALYSIS_ATTRS = {
    "expected_bundle": attr.label(mandatory = True, providers = [XlsArtifactBundleInfo]),
    "source": attr.label(mandatory = True, allow_single_file = True),
    "target_name": attr.string(mandatory = True),
}

default_conversion_analysis_test = analysistest.make(
    _conversion_analysis_test_impl,
    attrs = _ANALYSIS_ATTRS,
    config_settings = {"//command_line_option:extra_toolchains": ["@rules_xlsynth_selftest_xls_toolchain//:toolchain"]},
)

alternate_conversion_analysis_test = analysistest.make(
    _conversion_analysis_test_impl,
    attrs = _ANALYSIS_ATTRS,
    config_settings = {"//command_line_option:extra_toolchains": ["@workspace_override_xls_toolchain//:toolchain"]},
)
