# Environment Helpers

`env_helpers.py` hosts the Python entry point that Bazel actions use to talk to the xlsynth
toolchain. When the program starts it harvests a handful of `XLSYNTH_*` variables from the
action environment. The values drive two behaviours: building a temporary `toolchain.toml` file
for driver invocations and deriving additional command-line flags for individual tools. Regular
strings such as `XLSYNTH_GATE_FORMAT` become TOML string fields, while boolean variables like
`XLSYNTH_USE_SYSTEM_VERILOG` are validated and converted into `true` or `false`. For dslx tools
the helper injects the path to the bundled standard library and threads through optional warning
and type-inference settings. The module exposes two subcommands. `driver` shells out to the
`xlsynth-driver` binary, passing the generated TOML file and forwarding any extra user
arguments. `tool` directly executes a requested binary from the downloaded toolset after
pre-pending any extra flags determined from the environment.

# Generating the Bazel Helper

`make_env_helpers.py` keeps the Starlark side of the repository in sync with the Python runner.
The script reads `env_helpers.py`, wraps the source in a Starlark function called
`python_runner_source`, and writes the result to `env_helpers.bzl`. Embedding the literal Python
string this way lets each Bazel action materialise the runner directly as a declared tool rather
than depending on a separate source file target (we don't want our Python runner becoming a
source file dependency of all the rules written by users), which gives hermeticity guarantees
about the helper version used inside the sandbox. The docstring embedded into that function
documents the runner’s responsibilities so that Bazel authors do not need to open the Python
implementation to understand it. A unit test asserts that the generated file matches the
checked-in version, so running `python make_env_helpers.py` is the required regeneration step
when the runner changes.

# Bazel Integration Path

Many Starlark rules load `python_runner_source` and materialise the runner inside the action
sandbox. Each rule writes the helper script to a temporary output, adds it to the action’s tool
inputs, and then calls it with either the `driver` or `tool` subcommand depending on the
workflow. For example, `dslx_to_ir.bzl` composes the runner with `driver dslx2ir` to build
intermediate representations, then calls `driver ir2opt` for optimisation passes. Because every
action invokes the same runner binary, rule authors can rely on environment variables (for
custom DSLX search paths, enabling warnings, or toggling SystemVerilog emission) to behave
consistently across all tool stages.
