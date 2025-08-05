# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")
load(":helpers.bzl", "get_driver_path", "get_srcs_from_deps", "get_srcs_from_lib", "write_executable_shell_script")

def _dslx_test_impl(ctx):
    """
    Implements a test rule that runs a DSLX interpreter on the given DSLX library sources.

    Args:
      ctx: The context for this rule.

    Returns:
      A struct representing the result of this rule, including any run actions.
    """
    if ctx.attr.src and ctx.attr.lib:
        fail("Don't provide both src and lib.")
    if not ctx.attr.src and not ctx.attr.lib and len(ctx.attr.deps) != 1:
        fail("Must provide src or lib with zero or more dependencies; alternatively, provide exactly one dependency.")

    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir = env.get("XLSYNTH_TOOLS")
    if not xlsynth_tool_dir:
        fail("Please set XLSYNTH_TOOLS environment variable")

    # Ensure the interpreter binary exists
    xlsynth_tool_dir, _xlsynth_driver_file = get_driver_path(ctx)
    dslx_interpreter_file = xlsynth_tool_dir + "/dslx_interpreter_main"

    if ctx.attr.src:
        test_src = [ctx.file.src]
    elif ctx.attr.lib:
        test_src = get_srcs_from_lib(ctx)
    else:
        test_src = []

    # The order of the srcs matters. dslx_interpreter_main runs tests from the first file.
    srcs = test_src + get_srcs_from_deps(ctx)

    flags_str = "--compare=jit --alsologtostderr --dslx_stdlib_path=" + xlsynth_tool_dir + "/xls/dslx/stdlib"

    additional_dslx_paths = env.get("XLSYNTH_DSLX_PATH")
    if additional_dslx_paths:
        flags_str += " --dslx_path=" + additional_dslx_paths

    enable_warnings = env.get("XLSYNTH_DSLX_ENABLE_WARNINGS")
    if enable_warnings:
        flags_str += " --enable_warnings=" + enable_warnings

    disable_warnings = env.get("XLSYNTH_DSLX_DISABLE_WARNINGS")
    if disable_warnings:
        flags_str += " --disable_warnings=" + disable_warnings

    # If requested, enable the v2 type-inference pass.
    type_inference_v2 = env.get("XLSYNTH_TYPE_INFERENCE_V2")
    if type_inference_v2 == "true":
        flags_str += " --type_inference_v2=true"
    elif type_inference_v2 in (None, "", "false"):
        pass  # v1 remains the default
    else:
        fail("Invalid value for XLSYNTH_TYPE_INFERENCE_V2: {}".format(type_inference_v2))

    cmd = dslx_interpreter_file + " " + flags_str + " " + " ".join([src.path for src in srcs])

    runfiles = ctx.runfiles(srcs)
    executable_file = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + ".sh",
        cmd = cmd,
    )
    return DefaultInfo(
        runfiles = runfiles,
        files = depset(direct = [executable_file]),
        executable = executable_file,
    )

dslx_test = rule(
    doc = "Test a DSLX module using the interpreter.",
    implementation = _dslx_test_impl,
    attrs = {
        "src": attr.label(
            doc = "The DSLX source module to be tested. Use either src or lib, but not both. If there is only one module, you may instead use deps.",
            allow_files = [".x"],
        ),
        "lib": attr.label(
            doc = "The DSLX library to be tested. Use either src or lib, but not both. If there is only one module, you may instead use deps.",
            providers = [DslxInfo],
        ),
        "deps": attr.label_list(
            doc = "The DSLX library dependencies for the test.",
            providers = [DslxInfo],
        ),
    },
    test = True,
)
