# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":helpers.bzl", "get_srcs_from_lib")
load(":ir_provider.bzl", "IrInfo")
load(
    ":xls_toolchain.bzl",
    "XlsArtifactBundleInfo",
    "declare_xls_toolchain_toml",
    "get_selected_tools_toolchain",
    "get_tool_artifact_inputs",
)

def _dslx_to_ir_impl(ctx):
    main_src = ctx.attr.lib[DslxInfo].root

    all_transitive_srcs = get_srcs_from_lib(ctx)

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = get_selected_tools_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "dslx_to_ir", toolchain = toolchain)
    dslx2ir_inputs = [toolchain_file] + get_tool_artifact_inputs(toolchain, "ir_converter_main")
    ir2opt_inputs = [toolchain_file] + get_tool_artifact_inputs(toolchain, "opt_main")

    # Conversion selects and marks the package top, including elaborated procs.
    ctx.actions.run(
        inputs = all_transitive_srcs + dslx2ir_inputs,
        executable = runner,
        outputs = [ctx.outputs.ir_file],
        arguments = [
            "tool",
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "--toolchain",
            toolchain_file.path,
            "--stdout_path",
            ctx.outputs.ir_file.path,
            "ir_converter_main",
            main_src.path,
            "--top",
            ctx.attr.top,
            "--convert_tests=false",
        ],
        use_default_shell_env = False,
        progress_message = "Generating IR for DSLX",
        mnemonic = "DSLX2IR",
    )

    # Optimize the exact converted package using its marked top. Its IR name
    # need not follow the naming convention for a pure DSLX function.
    ctx.actions.run(
        inputs = [ctx.outputs.ir_file] + ir2opt_inputs,
        executable = runner,
        outputs = [ctx.outputs.opt_ir_file],
        arguments = [
            "tool",
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "--toolchain",
            toolchain_file.path,
            "--stdout_path",
            ctx.outputs.opt_ir_file.path,
            "opt_main",
            ctx.outputs.ir_file.path,
        ],
        use_default_shell_env = False,
        progress_message = "Optimizing IR",
        mnemonic = "IR2OPT",
    )

    return IrInfo(
        ir_file = ctx.outputs.ir_file,
        opt_ir_file = ctx.outputs.opt_ir_file,
    )

dslx_to_ir = rule(
    doc = "Convert a DSLX function or proc to raw and optimized IR packages.",
    implementation = _dslx_to_ir_impl,
    attrs = {
        "lib": attr.label(
            doc = "The DSLX library to be converted to IR.",
            providers = [DslxInfo],
            mandatory = True,
        ),
        "top": attr.string(
            doc = "The DSLX function or proc in the library's root module to convert.",
            mandatory = True,
        ),
        "xls_bundle": attr.label(
            doc = "Optional XLS bundle override.",
            providers = [XlsArtifactBundleInfo],
        ),
    },
    outputs = {
        "ir_file": "%{name}.ir",
        "opt_ir_file": "%{name}.opt.ir",
    },
    toolchains = ["//:toolchain_type"],
)
