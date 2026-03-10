# Toolchain Helpers

`env_helpers.py` hosts the Python entry point that Bazel actions use to talk to the xlsynth
toolchain. Bazel rules materialise a per-action `toolchain.toml` file from the
registered `rules_xlsynth` toolchain plus any rule-level overrides, then pass
that declared input to the runner. The runner exposes two subcommands:
`driver` shells out to the configured `xlsynth-driver` binary with
`--toolchain=<path>`, while `tool` reads the same TOML file and derives the
extra DSLX flags needed by direct tool invocations such as
`dslx_interpreter_main` or `typecheck_main`.

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
sandbox. Each rule writes the helper script to a temporary output, writes a
declared TOML file for the configured toolchain, and then calls the helper with
either the `driver` or `tool` subcommand depending on the workflow. For
example, `dslx_to_ir.bzl` composes the runner with `driver dslx2ir` to build
intermediate representations, then calls `driver ir2opt` for optimisation
passes. Tool selection and repo-wide defaults come from the registered Bazel
toolchain instead of `XLSYNTH_*` action environment variables.
