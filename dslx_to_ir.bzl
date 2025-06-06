# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_driver_path", "get_srcs_from_lib", "mangle_dslx_name", "write_config_toml")
load(":ir_provider.bzl", "IrInfo")

def _dslx_to_ir_impl(ctx):
    xlsynth_tool_dir, xlsynth_driver_file = get_driver_path(ctx)

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

    config_file = write_config_toml(ctx, xlsynth_tool_dir)

    cmd = "{driver} --toolchain={toolchain} dslx2ir --dslx_input_file={src} --dslx_top={top} > {output}".format(
        driver = xlsynth_driver_file,
        toolchain = config_file.path,
        src = main_src.path,
        top = ctx.attr.top,
        output = ctx.outputs.ir_file.path,
    )

    all_transitive_srcs = get_srcs_from_lib(ctx)

    ctx.actions.run(
        inputs = all_transitive_srcs + [config_file],
        outputs = [ctx.outputs.ir_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
        use_default_shell_env = True,
        progress_message = "Generating IR for DSLX",
        mnemonic = "DSLX2IR",
    )

    ir_top = mangle_dslx_name(main_src.basename, ctx.attr.top)

    # Now we optimize that (unoptimized) IR file.

    cmd = "{driver} --toolchain={toolchain} ir2opt {src} --top {ir_top} > {output}".format(
        driver = xlsynth_driver_file,
        toolchain = config_file.path,
        src = ctx.outputs.ir_file.path,
        ir_top = ir_top,
        output = ctx.outputs.opt_ir_file.path,
    )

    ctx.actions.run(
        inputs = [ctx.outputs.ir_file] + [config_file],
        outputs = [ctx.outputs.opt_ir_file],
        arguments = ["-c", cmd],
        executable = "/bin/sh",
        use_default_shell_env = True,
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
)
