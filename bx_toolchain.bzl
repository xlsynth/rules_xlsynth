# SPDX-License-Identifier: Apache-2.0

"""Shared action setup for BX and block IR rules."""

load("@bazel_skylib//lib:shell.bzl", "shell")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs")

_COMMAND_MINIMUM_VERSIONS = {
    "block2sv": (0, 69, 0),
    "bx-prove-invariant": (0, 82, 0),
    "bx-prove-quickcheck": (0, 82, 0),
    "bx-test": (0, 82, 0),
    # Both commands first accepted --warnings-as-errors in 0.81.0.
    "bx2gv": (0, 81, 0),
    "bx2ir": (0, 81, 0),
}

def require_bx_toolchain(toolchain, command):
    """Rejects a known release pin that predates the driver command.

    Args:
      toolchain: Selected XLS toolchain.
      command: Driver subcommand to check.
    """
    pin = getattr(toolchain, "xlsynth_crate_pin", None)
    if pin == None or pin.kind != "release_tag":
        return
    parts = pin.value[1:].split("+", 1)[0].split("-", 1)[0].split(".")
    if len(parts) != 3 or not all([part.isdigit() for part in parts]):
        return
    minimum = _COMMAND_MINIMUM_VERSIONS[command]
    if (int(parts[0]), int(parts[1]), int(parts[2])) < minimum:
        fail("{} needs xlsynth-driver {}.{}.{} or later, but the selected bundle pins {}. Select a newer bundle with xls_bundle or register it as the workspace toolchain.".format(
            command,
            minimum[0],
            minimum[1],
            minimum[2],
            pin.value,
        ))

def bx_runtime_env(library_path):
    """Sets the dynamic library search path on Linux and macOS."""
    return {"LD_LIBRARY_PATH": library_path, "DYLD_LIBRARY_PATH": library_path}

def _shell_execroot_path(path):
    return '"$execroot/"' + shell.quote(path)

def run_bx_driver(
        ctx,
        toolchain,
        *,
        command,
        inputs,
        arguments,
        output,
        mnemonic,
        output_flag = None,
        path_arguments = {},
        working_directory = None):
    """Runs a BX or block IR driver command to produce one artifact.

    Args:
      ctx: Rule context.
      toolchain: Selected XLS toolchain.
      command: Driver subcommand to run.
      inputs: Design inputs to declare on the action.
      arguments: Arguments to pass to the subcommand.
      output: Declared output file.
      mnemonic: Bazel action mnemonic.
      output_flag: Optional driver flag for writing to a file. Otherwise capture stdout.
      path_arguments: Driver options mapped to input files in the execroot.
      working_directory: Optional directory relative to the execroot for import resolution.
    """
    toolchain_file = declare_xls_toolchain_toml(ctx, name = command, toolchain = toolchain)
    inputs = inputs + [toolchain_file] + get_driver_artifact_inputs(toolchain)
    arguments = [command] + arguments
    files = dict(path_arguments)
    if output_flag:
        files[output_flag] = output
    if output_flag and not working_directory and toolchain.libxls.extension != "dylib":
        ctx.actions.run(
            inputs = inputs,
            outputs = [output],
            executable = toolchain.driver,
            arguments = ["--toolchain=" + toolchain_file.path] + arguments + [flag + "=" + file.path for flag, file in files.items()],
            env = dict(bx_runtime_env(toolchain.runtime_library_path), XLSYNTH_TOOLS = toolchain.tools_path),
            mnemonic = mnemonic,
        )
        return

    # Set the loader paths after Bazel's macOS sandbox launcher, which can
    # strip DYLD_LIBRARY_PATH before the action starts.
    env = bx_runtime_env(_shell_execroot_path(toolchain.runtime_library_path))
    env["XLSYNTH_TOOLS"] = _shell_execroot_path(toolchain.tools_path)
    script = ["set -e", 'execroot="$PWD"']
    script.extend(["export " + name + "=" + value for name, value in env.items()])
    if working_directory:
        script.append("cd " + _shell_execroot_path(working_directory))
    driver = " ".join([
        "exec",
        _shell_execroot_path(toolchain.driver_path),
        "--toolchain=" + _shell_execroot_path(toolchain_file.path),
        '"$@"',
    ] + [flag + "=" + _shell_execroot_path(file.path) for flag, file in files.items()])
    if not output_flag:
        driver += " > " + _shell_execroot_path(output.path)
    script.append(driver)
    ctx.actions.run_shell(
        inputs = inputs,
        outputs = [output],
        arguments = arguments,
        command = "\n".join(script),
        mnemonic = mnemonic,
    )
