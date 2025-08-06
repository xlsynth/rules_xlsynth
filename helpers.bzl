# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")

def write_executable_shell_script(ctx, filename, cmd, env_exports = None):
    """Writes a shell script that executes the given command and returns a handle to it.

    Args:
        ctx: The context object.
        filename: The name of the file to write.
        cmd: The command to execute.
        env_exports: A dictionary of environment variables to export.
    """
    executable_file = ctx.actions.declare_file(filename)
    content = "\n".join([
            "#!/usr/bin/env bash",
            "set -e",
            #"set -ex",
            #"ls -alR",
            #"pwd",
        ]) + "\n"
    if env_exports:
        for key, value in env_exports.items():
            content += "export {}={}\n".format(key, value)
    content += cmd
    ctx.actions.write(
        output = executable_file,
        content = content,
        is_executable = True,
    )
    return executable_file

def _get_srcs_from(dslx_info_providers):
    # Get DAG entries from DslxInfo. Returns a list where index 0 is the root module.
    dag_entries = []
    for item in dslx_info_providers:
        dag_entries.extend(item[DslxInfo].dag.to_list())

    srcs = []
    for entry in dag_entries:
        srcs += [src for src in list(entry.srcs)]

    srcs = list(reversed(srcs))
    return srcs

def get_srcs_from_deps(ctx):
    """Helper for the case where there's a deps attr that is a sequence of DSLX info providers."""
    return _get_srcs_from(ctx.attr.deps)

def get_srcs_from_lib(ctx):
    """Helper for the case where there's a lib attr that is a DSLX info provider."""
    return _get_srcs_from([ctx.attr.lib])

def mangle_dslx_name(basename, top):
    no_ext = basename.split(".")[0]
    return "__" + no_ext + "__" + top
