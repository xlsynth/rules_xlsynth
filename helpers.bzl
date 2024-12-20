# SPDX-License-Identifier: Apache-2.0

load(":dslx_provider.bzl", "DslxInfo")

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

def get_driver_path(ctx):
    env = ctx.configuration.default_shell_env
    xlsynth_tool_dir = env.get("XLSYNTH_TOOLS")
    if not xlsynth_tool_dir:
        fail("Please set XLSYNTH_TOOLS environment variable")
    xlsynth_driver_dir = env.get("XLSYNTH_DRIVER_DIR")
    if not xlsynth_driver_dir:
        fail("Please set XLSYNTH_DRIVER_DIR environment variable")

    # Ensure the interpreter binary exists
    xlsynth_driver_file = xlsynth_driver_dir + "/xlsynth-driver"
    return xlsynth_tool_dir, xlsynth_driver_file

def get_srcs_from_deps(ctx):
    # Get DAG entries from DslxInfo
    dag_entries = []
    for dep in ctx.attr.deps:
        dag_entries.extend(dep[DslxInfo].dag.to_list())

    srcs = []
    for entry in dag_entries:
        srcs += [src for src in list(entry.srcs)]

    srcs = list(reversed(srcs))
    return srcs

def write_config_toml(ctx, xlsynth_tool_dir):
    env = ctx.configuration.default_shell_env
    # Define the configuration file contents
    dslx_stdlib_path = xlsynth_tool_dir + "/xls/dslx/stdlib"
    tool_path = xlsynth_tool_dir
    additional_dslx_paths = env.get("XLSYNTH_DSLX_PATH", "")
    additional_dslx_paths_list = additional_dslx_paths.split(":")
    additional_dslx_paths_toml = ", ".join([repr(s) for s in additional_dslx_paths_list])

    config_file_content = """[toolchain]
dslx_stdlib_path = "{}"
tool_path = "{}"
dslx_path = [{}]
""".format(dslx_stdlib_path, tool_path, additional_dslx_paths_toml)

    # Write the configuration file
    config_file = ctx.actions.declare_file(ctx.label.name + "_config.toml")
    ctx.actions.write(
        output=config_file,
        content=config_file_content,
        is_executable = False,
    )
    return config_file


def mangle_dslx_name(basename, top):
    no_ext = basename.split(".")[0]
    return "__" + no_ext + "__" + top
