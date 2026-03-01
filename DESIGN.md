# Workspace toolchain design

`rules_xlsynth` now exposes one public XLS artifact-selection surface: the
`xls` module extension. A Bazel workspace chooses one or more named bundles in
`MODULE.bazel`, publishes them with `use_repo(...)`, and registers one default
bundle with `register_toolchains("@<name>//:all")`. Public artifact selection
no longer lives in `.bazelrc` `@rules_xlsynth//config:{driver_path,tools_path,runtime_library_path,dslx_stdlib_path}`
flags.

## Bundle repos and exported targets

Each `xls.toolchain(...)` call materializes a repo that contains the selected
tool binaries, the DSLX stdlib tree, the matching `xlsynth-driver`, and the
matching `libxls` shared library. That repo exports:

- `@<name>//:all`
- `@<name>//:bundle`
- `@<name>//:libxls`
- `@<name>//:libxls_link`
- `@<name>//:dslx_stdlib`

`artifact_source` controls how those artifacts are resolved:

- `auto` prefers exact-version `/eda-tools` installs and otherwise downloads
  the release artifacts.
- `eda_tools_only` requires the matching `/eda-tools` install.
- `download_only` always downloads the release artifacts.
- `local_paths` uses explicit local paths and is the documented escape hatch
  for `/tmp/xls-local-dev/` style setups.

## Default bundles and explicit overrides

Most rules use the registered default workspace bundle through normal Bazel
toolchain resolution. Supported leaf rules can opt into a named bundle with
`xls_bundle = "@<name>//:bundle"`. That override changes only the artifact
bundle. The existing behavior settings - for example `dslx_path`, warnings,
`type_inference_v2`, `gate_format`, `assert_format`, `use_system_verilog`, and
`add_invariant_assertions` - still come from the registered toolchain.

## Runner and toolchain TOML

`env_helpers.py` hosts the Python entry point that Bazel actions use to talk to
the xlsynth toolchain. Bazel rules materialize a per-action
`xlsynth-toolchain.toml` file from the selected bundle plus any rule-level
behavior overrides, then pass that declared input to the runner. The runner
exposes two subcommands: `driver` shells out to the configured
`xlsynth-driver` binary with `--toolchain=<path>`, while `tool` reads the same
TOML file and derives the extra DSLX flags needed by direct tool invocations
such as `dslx_interpreter_main` or `typecheck_main`.

The helper uses the selected `libxls` file path directly and derives the
runtime library directory from `dirname(libxls_path)`, so users no longer need
to configure a separate runtime-library path. The old artifact-path build
settings are deleted; artifact selection is bundle-only.

## Generating the Bazel helper

`make_env_helpers.py` keeps the Starlark side of the repository in sync with
the Python runner. The script reads `env_helpers.py`, wraps the source in a
Starlark function called `python_runner_source`, and writes the result to
`env_helpers.bzl`. Embedding the literal Python string this way lets each Bazel
action materialize the runner directly as a declared tool rather than depending
on a separate source file target, which gives hermeticity guarantees about the
helper version used inside the sandbox. A unit test asserts that the generated
file matches the checked-in version, so running `python make_env_helpers.py` is
the required regeneration step when the runner changes.

## Bazel integration path

Many Starlark rules load `python_runner_source` and materialize the runner
inside the action sandbox. Each rule writes the helper script to a temporary
output, writes a declared TOML file for the configured toolchain, and then
calls the helper with either the `driver` or `tool` subcommand depending on the
workflow. For example, `dslx_to_ir.bzl` composes the runner with
`driver dslx2ir` to build intermediate representations, then calls
`driver ir2opt` for optimization passes. Artifact selection now comes from the
module-extension bundle instead of `XLSYNTH_*` action environment variables or
artifact-path build settings.
