# Workspace toolchain design

`rules_xlsynth` now exposes one public XLS artifact-selection surface: the
`xls` module extension. A Bazel workspace chooses one or more named bundles in
`MODULE.bazel`, publishes the generated runtime and toolchain repos with
`use_repo(...)`, and registers one default toolchain repo with
`register_toolchains("@<name>_toolchain//:all")`. Public artifact selection
no longer lives in `.bazelrc` `@rules_xlsynth//config:{driver_path,tools_path,runtime_library_path,dslx_stdlib_path}`
flags.

## Bundle repos and exported targets

Each `xls.toolchain(...)` call exposes one runtime repo and one toolchain repo.
`@<name>_runtime` contains the selected tool binaries, the DSLX stdlib tree,
the matching `libxls` shared library, and the runtime-facing exports.
`@<name>_toolchain` contains the `:bundle` target, the registered toolchain
target, and a declared `:xlsynth-driver` target. Loading or registering the
toolchain repo is metadata-only; the driver target copies, validates,
downloads, or installs `xlsynth-driver` only when `:xlsynth-driver` is built
directly or a rule action consumes the driver from `:bundle`. The public split
is:

- `@<name>_runtime//:libxls`
- `@<name>_runtime//:libxls_link`
- `@<name>_runtime//:dslx_stdlib`
- `@<name>_runtime//:xlsynth_sys_artifact_config`
- `@<name>_runtime//:xlsynth_sys_legacy_stdlib`
- `@<name>_runtime//:xlsynth_sys_legacy_dso`
- `@<name>_runtime//:xlsynth_sys_dep`
- `@<name>_runtime//:xlsynth_sys_runtime_files`
- `@<name>_runtime//:xlsynth_sys_link_dep`
- `@<name>_runtime//:libxls_runtime_files`
- `@<name>_toolchain//:xlsynth-driver`
- `@<name>_toolchain//:bundle`
- `@<name>_toolchain//:toolchain`

Workspaces still register the selected default with
`register_toolchains("@<name>_toolchain//:all")`; that is the registration
pattern for the package, not a separate exported target. When a local or
installed driver path is configured, the module extension creates a private
generated repo that exposes that host driver file as a declared input to
`@<name>_toolchain//:xlsynth-driver`. Downstream workspaces do not use that
repo directly.

The `xlsynth_sys_*` exports are the intended downstream contract for
`rules_rust` `crate_extension.annotation(...)` wiring. The preferred modern
shape is `build_script_data` / `build_script_env` for the build-script
contract, plus `deps = ["@<name>_runtime//:xlsynth_sys_dep"]` for the combined
runtime-plus-link contract. The compatibility exports
`xlsynth_sys_runtime_files` and `xlsynth_sys_link_dep` remain available for
callers that still spell those phases separately. This lets root `MODULE.bazel`
files choose only a bundle and a build-script mode instead of coupling to
generic bundle internals.

`artifact_source` controls how those artifacts are resolved:

- `auto` probes a consumer-owned installed layout and otherwise downloads the
  release artifacts.
- `installed_only` requires the matching installed layout.
- `download_only` always downloads the release artifacts.
- `local_paths` uses explicit local paths and is the documented escape hatch
  for `/tmp/xls-local-dev/` style setups.

For the installed-layout modes, runtime materialization derives the concrete
tools and library paths from the toolchain declaration instead of hard-coding a
repository-global install root: `<installed_tools_root_prefix>/v<xls_version>`
for the tools tree, DSLX stdlib, and `libxls`. Driver materialization derives
`<installed_driver_root_prefix>/<xlsynth_driver_version>/bin/xlsynth-driver`
inside the declared driver target. The provider owns the version-derived
suffixes; the consumer workspace owns the root prefixes.

For `local_paths`, runtime materialization uses `local_tools_path`,
`local_dslx_stdlib_path`, and `local_libxls_path`. The local driver path is
needed only by driver-backed actions. This lets runtime consumers depend on
`@<name>_runtime` or register `@<name>_toolchain` without materializing,
probing, downloading, or compiling `xlsynth-driver`.

## Resolved producer identity

Consumers that mint durable identities can set `emit_resolved_identity = True`.
The runtime repository creates `resolved_identity.json` as a private input
visible only to its paired generated toolchain repository. Public runtime
providers do not carry identity. The generated driver action validates its
selected `xlsynth-crate` pin and the manifest's internal pin relationships,
then emits the identity sidecar exported by the bundle. Consumers receive
producer identity only through `XlsArtifactBundleInfo`, which keeps the
executed bundle and its producer identity in one Bazel-owned handoff instead of
asking a downstream action to restate or pair identity separately.
Identity-bearing driver targets are valid only at the generated root targets in
the canonical paired `*_runtime` and `*_toolchain` repositories. This rejects
hand-written public-rule assembly before action execution.

The manifest records typed `xlsynth-crate` and XLS pins, exact resolved source
revisions, the published XLS release used for artifacts, and the XLS release
implied by the selected crate's `xlsynth-sys/build.rs`. Crate releases and XLS
releases are independently versioned; matching version text is not a binding
rule. By default, identity materialization rejects an explicit XLS pin that
does not resolve to the crate-implied XLS release.
`allow_xls_pin_mismatch = True` is reserved for deliberate development
overrides. Trusted identity emission requires `artifact_source =
"download_only"`: the installed-layout modes intentionally trust
consumer-owned directories and therefore cannot mint an authoritative archive
identity.

An exact `xlsynth_driver_git_revision` is materialized by Cargo
`--git ... --rev <SHA>`. Reusing an installed Git-pinned driver additionally
requires an adjacent provenance record that binds the canonical source
repository, exact revision, and driver digest. `auto` reinstalls if that proof
is missing or stale, while `installed_only` fails. An exact `xls_git_revision`
reuses published release artifacts only when the SHA maps to one published XLS
release tag. Building arbitrary XLS source revisions is intentionally outside
this contract. `local_paths` remains useful for non-provenance-sensitive
development but cannot emit trusted resolved identity.

The trusted handoff assumes the consumer controls the selected
`rules_xlsynth` source and module graph. It is not cryptographic attestation
against a root module that replaces `rules_xlsynth`, overrides generated
repositories, or deliberately constructs a lying fork.

## Default bundles and explicit overrides

Most rules use the registered default workspace bundle through normal Bazel
toolchain resolution. Supported DSLX rules can opt into a named bundle with
`xls_bundle = "@<name>_toolchain//:bundle"`. That override changes only the artifact
bundle. The existing behavior settings - for example `dslx_path`, warnings,
`gate_format`, `assert_format`, `use_system_verilog`, and
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
