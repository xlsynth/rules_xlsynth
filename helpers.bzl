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
            # Note: these are left in on purpose to help us remember what magic incantations can help
            # us to debug the bash script's execution environment.
            # ```
            # "set -ex",
            # "ls -alR",
            # "pwd",
            # ```
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
    # Source closure only: callers select the module from DslxInfo.root.
    return depset(transitive = [item[DslxInfo].transitive_srcs for item in dslx_info_providers]).to_list()

def get_dslx_input(ctx):
    """Resolves src/lib/single-dependency forms to a root and complete source inputs."""
    source = getattr(ctx.file, "src", None)
    library = ctx.attr.lib
    libraries = ([library] if library else []) + ctx.attr.deps
    srcs = _get_srcs_from(libraries)
    if source and library:
        fail("Don't provide both src and lib.")
    elif source:
        if source in srcs:
            fail("Don't provide the test through more than one attribute: src/lib/deps.")
        root = source
        srcs = [source] + srcs
    elif library:
        root = library[DslxInfo].root
    elif len(ctx.attr.deps) == 1:
        root = ctx.attr.deps[0][DslxInfo].root
    else:
        fail("must specify lib or exactly one dependency")
    return struct(root = root, srcs = srcs)

def get_srcs_from_lib(ctx):
    """Returns the selected library's source closure, without root-order semantics."""
    return _get_srcs_from([ctx.attr.lib])

def mangle_dslx_name(basename, top):
    no_ext = basename.split(".")[0]
    return "__" + no_ext + "__" + top
