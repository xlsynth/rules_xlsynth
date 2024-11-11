def write_executable_shell_script(ctx, filename, cmd):
    """Writes a shell script that executes the given command and returns a handle to it."""
    executable_file = ctx.actions.declare_file(filename)
    ctx.actions.write(
        output = executable_file,
        content = "\n".join([
            "#!/usr/bin/env bash",
            "set -e",
            #"set -ex",
            #"ls -alR",
            #"pwd",
            cmd,
        ]),
        is_executable = True,
    )
    return executable_file

