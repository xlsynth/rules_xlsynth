load(":helpers.bzl", "write_executable_shell_script")

def _dslx_format_impl(ctx):
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir = env.get("XLSYNTH_TOOLS")
    if not xlsynth_tool_dir:
        fail("Please set XLSYNTH_TOOLS environment variable")

    # Ensure the interpreter binary exists
    dslx_fmt_file = xlsynth_tool_dir + "/dslx_fmt"

    src_depset_files = ctx.attr.srcs

    input_files = []
    formatted_files = []

    for src in src_depset_files:
        input_file = src[DefaultInfo].files.to_list()[0]
        input_files.append(input_file)
        formatted_file = ctx.actions.declare_file(input_file.basename + ".fmt")
        formatted_files.append(formatted_file)

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

    # Create an executable shell script to run the diff check for all files
    diff_commands = []
    for input_file, formatted_file in zip(input_files, formatted_files):
        diff_cmd = "diff -u {} {} || (echo 'Formatting differs. Run: `{}/dslx_fmt -i {}` to fix formatting in place' && exit 1)".format(input_file.short_path, formatted_file.short_path, xlsynth_tool_dir, input_file.short_path)
        diff_commands.append(diff_cmd)

    diff_script_file = write_executable_shell_script(
        ctx = ctx,
        filename = ctx.label.name + "-diff.sh",
        cmd = '\n'.join(diff_commands),
    )

    return DefaultInfo(
        runfiles=ctx.runfiles(files=input_files + formatted_files + [diff_script_file]),
        files=depset(direct=[diff_script_file] + formatted_files),
        executable=diff_script_file,
    )

dslx_fmt_test = rule(
    implementation=_dslx_format_impl,
    attrs={
        "srcs": attr.label_list(allow_files=[".x"], allow_empty=False, doc="Source files to check formatting"),
    },
    doc="A rule that checks if the given DSLX files are properly formatted.",
    test=True,
)
