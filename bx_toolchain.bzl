# SPDX-License-Identifier: Apache-2.0

"""Shared action setup for BX and block IR rules."""

load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs")

_COMMAND_MINIMUM_VERSIONS = {
    "block2sv": (0, 69, 0),
    "bx-prove-invariant": (0, 82, 0),
    "bx-prove-quickcheck": (0, 82, 0),
    "bx-test": (0, 82, 0),
    "bx2gv": (0, 80, 0),
    "bx2ir": (0, 80, 0),
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

def run_bx_driver(ctx, toolchain, *, command, inputs, arguments, output, mnemonic):
    """Runs a BX or block IR driver command and captures its stdout.

    Args:
      ctx: Rule context.
      toolchain: Selected XLS toolchain.
      command: Driver subcommand to run.
      inputs: Design inputs to declare on the action.
      arguments: Arguments to pass to the subcommand.
      output: File to receive stdout.
      mnemonic: Bazel action mnemonic.
    """
    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = command, toolchain = toolchain)
    ctx.actions.run(
        inputs = inputs + [toolchain_file] + get_driver_artifact_inputs(toolchain),
        outputs = [output],
        executable = runner,
        arguments = [
            "driver",
            "--driver_path",
            toolchain.driver_path,
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "--toolchain",
            toolchain_file.path,
            "--stdout_path",
            output.path,
            command,
        ] + arguments,
        use_default_shell_env = False,
        mnemonic = mnemonic,
    )
