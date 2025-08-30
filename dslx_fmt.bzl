load(":helpers.bzl", "write_executable_shell_script")
load(":env_helpers.bzl", "python_runner_source")

def _dslx_format_impl(ctx):
    src_depset_files = ctx.attr.srcs

    input_files = []
    formatted_files = []

    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source())

    for src in src_depset_files:
        input_file = src[DefaultInfo].files.to_list()[0]
        input_files.append(input_file)
        formatted_file = ctx.actions.declare_file(input_file.basename + ".fmt")
        formatted_files.append(formatted_file)

        ctx.actions.run_shell(
            inputs=[input_file],
            tools=[runner],
            outputs=[formatted_file],
            command="\"$1\" tool dslx_fmt \"$2\" > \"$3\"",
            arguments=[
                runner.path,
                input_file.path,
                formatted_file.path,
            ],
            use_default_shell_env=True,
        )

    diff_commands = []
    for input_file, formatted_file in zip(input_files, formatted_files):
        diff_cmd = "diff -u {} {} || (echo 'Formatting differs. Run: `dslx_fmt -i {}` to fix formatting in place' && exit 1)".format(input_file.short_path, formatted_file.short_path, input_file.short_path)
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
