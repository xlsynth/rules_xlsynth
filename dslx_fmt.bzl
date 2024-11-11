load(":helpers.bzl", "write_executable_shell_script")

def _dslx_format_impl(ctx):
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir = env.get("XLSYNTH_TOOLS")
    if not xlsynth_tool_dir:
        fail("Please set XLSYNTH_TOOLS environment variable")

    # Ensure the interpreter binary exists
    dslx_fmt_file = xlsynth_tool_dir + "/dslx_fmt"

    src_depset_files = ctx.attr.src[DefaultInfo].files.to_list()
    if len(src_depset_files) != 1:
        fail("dslx_fmt_test requires a single source")
    src = src_depset_files[0]

    input_file = src
    formatted_file = ctx.actions.declare_file(src.basename + ".fmt")

    # Command to run the formatter and redirect stdout to the output file
    format_cmd = "{} {} > {}".format(dslx_fmt_file, input_file.path, formatted_file.path)

    # Create an action to run the formatter
    ctx.actions.run(
        inputs=[input_file],
        outputs=[formatted_file],
        executable="/bin/sh",
        arguments=["-c", format_cmd],
        use_default_shell_env=True,
    )

    # Create an executable shell script to run the diff check using absolute paths
    diff_cmd = "diff -u {} {} || (echo 'Formatting differs. Run: `{}/dslx_fmt -i {}` to fix formatting in place' && exit 1)".format(input_file.short_path, formatted_file.short_path, xlsynth_tool_dir, input_file.short_path)

    # Generate a shell script to perform the diff action, ensuring it runs after formatting
    diff_script_file = write_executable_shell_script(
        ctx = ctx,
	filename = ctx.label.name + "-diff-script.sh",
	cmd = diff_cmd,
    )

    return DefaultInfo(
        runfiles=ctx.runfiles(files=[input_file, formatted_file, diff_script_file]),
        files=depset(direct=[diff_script_file, formatted_file]),
        executable=diff_script_file,
    )

dslx_fmt_test = rule(
    implementation=_dslx_format_impl,
    attrs={
        "src": attr.label(allow_single_file=True, doc="Source file to check formatting"),
    },
    doc="A rule that checks if the given DSLX file is properly formatted.",
    test=True,
)
