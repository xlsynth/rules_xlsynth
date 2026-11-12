# SPDX-License-Identifier: Apache-2.0

"""Shared action setup for BX and block IR rules."""

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

def run_bx_driver(ctx, toolchain, *, command, inputs, arguments, output, mnemonic, output_flag = None):
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
    """
    toolchain_file = declare_xls_toolchain_toml(ctx, name = command, toolchain = toolchain)
    inputs = inputs + [toolchain_file] + get_driver_artifact_inputs(toolchain)
    arguments = ["--toolchain=" + toolchain_file.path, command] + arguments
    env = {"XLSYNTH_TOOLS": toolchain.tools_path}
    if output_flag:
        arguments = arguments + [output_flag, output.path]
    if output_flag and toolchain.libxls.extension != "dylib":
        ctx.actions.run(
            inputs = inputs,
            outputs = [output],
            executable = toolchain.driver,
            arguments = arguments,
            env = dict(env, **bx_runtime_env(toolchain.runtime_library_path)),
            mnemonic = mnemonic,
        )
    else:
        driver_exec = 'exec "$driver" "$@"'
        if not output_flag:
            driver_exec += ' > "$output"'
        ctx.actions.run_shell(
            inputs = inputs,
            outputs = [output],
            arguments = ["./" + toolchain.driver_path, output.path, toolchain.runtime_library_path] + arguments,
            # Set the loader paths after Bazel's macOS sandbox launcher, which
            # can strip DYLD_LIBRARY_PATH before the action starts.
            command = """
                driver="$1"
                output="$2"
                export LD_LIBRARY_PATH="$3"
                export DYLD_LIBRARY_PATH="$3"
                shift 3
            """ + driver_exec,
            env = env,
            mnemonic = mnemonic,
        )
