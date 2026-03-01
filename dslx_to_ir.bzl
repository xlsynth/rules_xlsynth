# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_srcs_from_lib", "mangle_dslx_name")
load(":ir_provider.bzl", "IrInfo")
load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "require_driver_toolchain")

def _dslx_to_ir_impl(ctx):
    # Get the DslxInfo from the direct library target
    lib_info = ctx.attr.lib[DslxInfo]
    # Convert the DAG depset to a list. The last element corresponds to the direct target due to postorder traversal.
    lib_dag_list = lib_info.dag.to_list()
    if not lib_dag_list:
        fail("DAG for library {} is empty".format(ctx.attr.lib.label))
    main_srcs = lib_dag_list[-1].srcs
    if len(main_srcs) != 1:
        fail("Expected exactly one source file for the library {}; got: {}".format(ctx.attr.lib.label, [s.path for s in main_srcs]))
    main_src = main_srcs[0]

    all_transitive_srcs = get_srcs_from_lib(ctx)

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = require_driver_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "dslx_to_ir")
    toolchain_inputs = [toolchain_file] + get_driver_artifact_inputs(toolchain)

    # Stage 1: dslx2ir
    ctx.actions.run(
        inputs = all_transitive_srcs + toolchain_inputs,
        executable = runner,
        outputs = [ctx.outputs.ir_file],
        arguments = [
            "driver",
            "--driver_path",
            toolchain.driver_path,
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "--toolchain",
            toolchain_file.path,
            "--stdout_path",
            ctx.outputs.ir_file.path,
            "dslx2ir",
            "--dslx_input_file",
            main_src.path,
            "--dslx_top",
            ctx.attr.top,
        ],
        use_default_shell_env = False,
        progress_message = "Generating IR for DSLX",
        mnemonic = "DSLX2IR",
    )

    ir_top = mangle_dslx_name(main_src.basename, ctx.attr.top)

    # Stage 2: ir2opt
    ctx.actions.run(
        inputs = [ctx.outputs.ir_file] + toolchain_inputs,
        executable = runner,
        outputs = [ctx.outputs.opt_ir_file],
        arguments = [
            "driver",
            "--driver_path",
            toolchain.driver_path,
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "--toolchain",
            toolchain_file.path,
            "--stdout_path",
            ctx.outputs.opt_ir_file.path,
            "ir2opt",
            ctx.outputs.ir_file.path,
            "--top",
            ir_top,
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
    doc = "Convert a DSLX file to IR",
    implementation = _dslx_to_ir_impl,
    attrs = {
        "lib": attr.label(
            doc = "The DSLX library to be converted to IR.",
            providers = [DslxInfo],
            mandatory = True,
        ),
        "top": attr.string(
            doc = "The top-level DSLX module to be converted to IR.",
            mandatory = True,
        ),
    },
    outputs = {
        "ir_file": "%{name}.ir",
        "opt_ir_file": "%{name}.opt.ir",
    },
    toolchains = ["//:toolchain_type"],
)
