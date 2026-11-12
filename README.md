# `rules_xlsynth`

[![CI](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml)

### Workspace toolchains

`rules_xlsynth` now selects XLS artifacts from `MODULE.bazel` through the `xls`
module extension. A workspace instantiates one or more named bundles with
`xls.toolchain(...)`, exposes the derived runtime and toolchain repos with
`use_repo(...)`, and registers one default toolchain repo with
`register_toolchains("@<name>_toolchain//:all")`.

```starlark
bazel_dep(name = "rules_xlsynth", version = "<release>")

xls = use_extension("@rules_xlsynth//:extensions.bzl", "xls")

xls.toolchain(
    name = "workspace_xls",
    xls_version = "0.54.7",
    xlsynth_driver_version = "0.66.0",
    artifact_source = "auto",
    installed_tools_root_prefix = "/opt/xlsynth",
    installed_driver_root_prefix = "/opt/xlsynth-driver",
)

xls.toolchain(
    name = "legacy_xls",
    xls_version = "0.37.0",
    xlsynth_driver_version = "0.32.0",
    artifact_source = "download_only",
)

use_repo(
    xls,
    "workspace_xls_runtime",
    "workspace_xls_toolchain",
    "legacy_xls_runtime",
    "legacy_xls_toolchain",
)
register_toolchains("@workspace_xls_toolchain//:all")
```

`artifact_source` chooses how each bundle repo is materialized:

- `auto` probes the consumer-owned installed layout and otherwise downloads the
  release artifacts.
- `installed_only` requires the matching installed layout.
- `download_only` always downloads the release artifacts.
- `local_paths` uses explicit paths supplied by the consumer workspace.

For the installed-layout modes, `rules_xlsynth` derives exact-version paths as:

- `<installed_tools_root_prefix>/v<xls_version>` for the tools tree
- `<installed_tools_root_prefix>/v<xls_version>/xls/dslx/stdlib` for the DSLX
  stdlib
- `<installed_tools_root_prefix>/v<xls_version>/libxls.{so,dylib}` for `libxls`
- `<installed_driver_root_prefix>/<xlsynth_driver_version>/bin/xlsynth-driver`
  for the driver binary

The attributes accepted by each mode are strict, but runtime and driver inputs
are resolved at different times:

- The runtime repo for `local_paths` requires `local_tools_path`,
  `local_dslx_stdlib_path`, and `local_libxls_path`. `local_driver_path` is
  required only when a driver-backed bundle/action is built.
- The runtime repo for `auto` and `installed_only` requires an XLS release pin
  through `xls_version` and `installed_tools_root_prefix`.
  `xlsynth_driver_version` and `installed_driver_root_prefix` are required only
  when a driver-backed bundle/action is built.
- `download_only` requires exactly one XLS release or Git pin through
  `xls_version` or `xls_git_revision`. A driver-backed bundle similarly requires
  exactly one `xlsynth_driver_version` or `xlsynth_driver_git_revision`.
- `local_paths` does not accept `xls_version` or `xlsynth_driver_version`;
  the other modes accept no local artifact overrides.
- `download_only` does not accept any `installed_*` attrs.

For provenance-sensitive consumers, `emit_resolved_identity = True` makes the
module extension emit `resolved_identity.json` in its generated runtime
repository. Public `xls_runtime_surface` targets remain non-identity surfaces.
The generated toolchain passes the same-repository manifest to the lazy driver
action, which validates it against the exact selected `xlsynth-crate` pin and
emits the sidecar exposed by the bundle provider. The manifest cannot be
attached to consumer-owned runtime inputs through the public runtime rule:
identity-bearing drivers are accepted only at the generated root targets in the
canonical paired `*_runtime` and `*_toolchain` repositories. Hand-written
identity-bearing driver targets fail analysis.
That manifest records typed `xlsynth-crate` and XLS pins, the exact resolved
source revisions, the published XLS release selected for artifacts, and the XLS
release implied by `xlsynth-sys/build.rs`. The two release namespaces are
independent: for example, an `xlsynth-crate` release may select a differently
numbered XLS release. Identity-capable bundles validate the implied and explicit
XLS releases by default; `allow_xls_pin_mismatch = True` is an explicit
development override. Trusted identity emission requires
`artifact_source = "download_only"` so the bundle cannot silently reuse
consumer-owned installed or local artifacts.

Identity-capable bundles may use `xlsynth_driver_git_revision = "<40-char SHA>"`
instead of `xlsynth_driver_version`; the lazy driver action then installs with
Cargo `--git ... --rev <SHA>`. Reusing an installed Git-pinned driver requires
an adjacent `xlsynth-driver.provenance.json` that binds the canonical source
repository, exact revision, and driver digest. `auto` reinstalls when that
proof is absent or stale; `installed_only` reports an error. They may use
`xls_git_revision = "<40-char SHA>"` instead of `xls_version` only when that
exact XLS SHA maps to one published `xlsynth/xlsynth` release tag. `local_paths`
bundles remain available for local development but cannot emit trusted resolved
identity.

This is a Bazel graph-integrity boundary, not a cryptographic attestation
against a consumer that replaces `rules_xlsynth`, overrides an
extension-generated repository, or otherwise controls the trusted module graph.
Provenance-sensitive consumers must pin and control the `rules_xlsynth` source
and generated module configuration, as Auto-SPO does.

Registering or loading `@<name>_toolchain` is metadata-only: it defines the
toolchain, bundle, and `xlsynth-driver` targets, but does not copy, execute,
download, or compile the driver. Driver materialization is a declared Bazel
action behind `@<name>_toolchain//:xlsynth-driver` and behind rule actions that
consume the driver from `@<name>_toolchain//:bundle`.

Download-backed driver actions have one host prerequisite: when `auto` falls
back to downloading the driver, or when `download_only` is selected and a
driver-backed action is built, that action installs `xlsynth-driver` with
`rustup run nightly cargo install`. The execution host must have `rustup`
available. If the nightly toolchain is missing, `rules_xlsynth` bootstraps a
repo-local `rustup` home before installing the driver.

Each `xls.toolchain(...)` call now exports two public repos:

- `@<name>_runtime` for runtime files, `xlsynth-sys` wiring, tools, and `libxls`
- `@<name>_toolchain` for `:bundle`, `:toolchain`, `:xlsynth-driver`, and
  the `@<name>_toolchain//:all` registration pattern

When a local or installed driver path is configured, the module extension
creates a private generated repo that exposes that host driver file as a
declared input to `@<name>_toolchain//:xlsynth-driver`. Downstream workspaces
do not use that repo directly or publish it with `use_repo(...)`.

The runtime repo exposes:

- `@<name>_runtime//:libxls` and `@<name>_runtime//:libxls_link` for native consumers
- `@<name>_runtime//:dslx_stdlib` for packages that need the standard library tree
- `@<name>_runtime//:xlsynth_sys_artifact_config` for the modern single-file
  `xlsynth-sys` build-script contract
- `@<name>_runtime//:xlsynth_sys_legacy_stdlib` and
  `@<name>_runtime//:xlsynth_sys_legacy_dso` for frozen `xlsynth-sys` releases that
  still use the paired `DSLX_STDLIB_PATH` / `XLS_DSO_PATH` contract
- `@<name>_runtime//:xlsynth_sys_dep` for the preferred `xlsynth-sys`
  runtime-plus-link contract
- `@<name>_runtime//:xlsynth_sys_runtime_files` and `@<name>_runtime//:xlsynth_sys_link_dep`
  as compatibility exports for callers that still spell runtime and link
  separately
- `@<name>_runtime//:libxls_runtime_files`, which now means the closed native
  runtime file set for the selected `libxls`

`xlsynth-sys` consumers should prefer `xlsynth_sys_artifact_config`,
`xlsynth_sys_dep`, and, for frozen releases, `xlsynth_sys_legacy_stdlib` plus
`xlsynth_sys_legacy_dso`, rather than spelling generic bundle internals like
`artifact_config`, `libxls_file`, `libxls`, or `dslx_stdlib` directly in
downstream `MODULE.bazel` files.

Supported DSLX rules may opt out of the registered default bundle with
`xls_bundle = "@<name>_toolchain//:bundle"`. Today that escape hatch is available on
`dslx_library`, `dslx_test`, `dslx_to_ir`, `dslx_prove_quickcheck_test`,
`dslx_to_sv_types`, `dslx_to_pipeline`, `dslx_to_pipeline_eco`, and
`dslx_stitch_pipeline`.

```starlark
dslx_to_pipeline(
    name = "legacy_pipeline",
    delay_model = "asap7",
    pipeline_stages = 1,
    top = "main",
    deps = [":my_dslx_library"],
    xls_bundle = "@legacy_xls_toolchain//:bundle",
)
```

Each `dslx_library` also exposes the producer pins selected by that specific
library. The public `DslxSelectedToolchainInfo` provider, exported by
`@rules_xlsynth//:rules.bzl`, contains `xls_pin`, `xlsynth_crate_pin`, and the
opt-in `metadata` output. A pipeline override does not change the toolchain
selected by its dependency. To select the legacy producer pins for a library,
apply the override to that library itself:

```starlark
dslx_library(
    name = "my_legacy_dslx_library",
    srcs = ["my_dslx_library.x"],
    xls_bundle = "@legacy_xls_toolchain//:bundle",
)
```

The overridden library reports XLS `v0.37.0` and XLSynth `v0.32.0`; a library
without its own override continues to report the registered default.

In Starlark, each available producer pin is a struct accessed through
`provider.xls_pin.kind` and `provider.xls_pin.value` or the corresponding
`provider.xlsynth_crate_pin` fields.

Request the machine-readable output without building the library's normal
typecheck output:

```shell
bazel build --output_groups=selected_toolchain //path:my_dslx_library
bazel build --output_groups=selected_toolchain //path:my_legacy_dslx_library
```

The generated `<target>.selected_toolchain.json` contains separately versioned
producer pins:

```json
{
  "schema_version": 1,
  "xls_pin": {"kind": "release_tag", "value": "v0.54.7"},
  "xlsynth_crate_pin": {"kind": "release_tag", "value": "v0.66.0"}
}
```

Git-pinned producers use `"kind": "git_revision"` with a lowercase,
40-character revision. Each producer is independently `null` when its identity
is unavailable, including versionless local bundles and older externally
defined toolchains. This output describes declared configuration and does not
authenticate executable contents. Trusted `resolved_identity.json` authenticates only
downloaded artifacts; neither metadata mechanism authenticates installed or
local executables.

Artifact-path build settings such as
`--@rules_xlsynth//config:driver_path=...`,
`--@rules_xlsynth//config:tools_path=...`,
`--@rules_xlsynth//config:runtime_library_path=...`, and
`--@rules_xlsynth//config:dslx_stdlib_path=...` are no longer supported.
Artifact selection lives only in `MODULE.bazel`. The remaining
`@rules_xlsynth//config:*` settings are behavior knobs, such as extra DSLX
search paths or warning toggles.

Self-hosted examples in this repo:

- `examples/workspace_toolchain_smoke/` shows one registered default bundle and
  one explicit `xls_bundle` override without any `.bazelrc` artifact flags.
- `examples/workspace_toolchain_local_dev/` shows a `local_paths` workspace
  rooted at `/tmp/xls-local-dev/`.

### `dslx_library`, `dslx_test` - libraries/tests for DSLX files

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_library", "dslx_test")

dslx_library(
    name = "my_dslx_library",
    srcs = ["my_dslx_library.x"],
)

# `dslx_test` can run all the inline tests in an associated library.
dslx_test(
    name = "my_dslx_library_test",
    deps = [":my_dslx_library"],
)
```

Libraries containing multiple source files must name their root module explicitly:

```starlark
dslx_library(
    name = "adder",
    root = "adder.x",
    srcs = ["adder.x", "optimized.x"],
)

dslx_test(
    name = "adder_test",
    lib = ":adder",
)
```

`root` must be one of the library's direct `srcs`. A single-source library may
omit it. Neither `srcs` nor `deps` ordering selects a module: all typechecking,
tests, proofs, and conversions use the declared root, with the other sources
available for imports. This does not separately typecheck unused source files.
`dslx_test(src = ..., deps = ...)` still selects the explicit test source.

`dslx_to_pipeline`, `dslx_to_pipeline_eco`, and `dslx_to_sv_types` accept `lib`
to select the root library and `deps` for additional inputs. Their existing
`deps = [":one_library"]` shorthand remains valid. Multiple dependencies without
`lib` are ambiguous and fail analysis.

Migration: multi-source libraries that previously relied on the last source
must add `root`; conversion rules that relied on the last dependency must add
`lib`. Custom rules using `DslxInfo` must use its `root` File and
`transitive_srcs` depset, which includes the root. The old `dag` field and DAG
construction functions have been removed. The source depset has no meaningful
ordering, and consumers must not infer a root from it.

Use `disable_warnings` to suppress warnings for one interpreter test:

```starlark
dslx_test(
    name = "my_dslx_library_unused_definition_test",
    lib = ":my_dslx_library",
    disable_warnings = ["unused_definition"],
)
```

This list adds to the suppressions configured with
`--@rules_xlsynth//config:disable_warnings=...`. It defaults to `[]` and affects
only this test invocation; building the library separately or running other
targets still uses their configured warning behavior.

### `dslx_fmt_test` - format DSLX files

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_fmt_test")

dslx_fmt_test(
    name = "dslx_fmt_test",
    srcs = glob(["*.x"]),
)
```

### `dslx_to_sv_types` - create `_pkg.sv` file

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_to_sv_types")

dslx_to_sv_types(
    name = "my_dslx_library_pkg",
    deps = [":my_dslx_library"],
    sv_enum_case_naming_policy = "unqualified",
    sv_struct_field_ordering = "as_declared",
)
```

`sv_enum_case_naming_policy` is required. Allowed values (matching
`xlsynth-driver`) are `unqualified` and `enum_qualified`.

`sv_struct_field_ordering` is optional. Allowed values are `as_declared`
(default) and `reversed`.

The selected bundle records whether its `xlsynth-driver` supports the
`--sv_enum_case_naming_policy` CLI flag. Older bundles still work with
`sv_enum_case_naming_policy = "unqualified"`; `enum_qualified` only works when
the chosen workspace bundle or explicit `xls_bundle` advertises support.

Older bundles also keep working with the default
`sv_struct_field_ordering = "as_declared"` behavior. The explicit `reversed`
mode only works when the chosen workspace bundle or explicit `xls_bundle`
advertises support for `--sv_struct_field_ordering`.

### `dslx_to_ir` - convert DSLX to optimized IR

Given a DSLX library target as a dependency, this rule will generate:

- an unoptimized IR file (simply IR converted DSLX); i.e. `my_dslx_library_ir.ir`
- an optimized IR file (optimized IR from the previous step); i.e. `my_dslx_library_ir.opt.ir`

for a given `top` entry point.

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_to_ir")

dslx_to_ir(
    name = "my_dslx_library_ir",
    lib = ":my_dslx_library",
    top = "main",
)
```

### BX libraries, Block IR, and SystemVerilog

BX describes RTL with explicit registers, enables, feedback, and block
instances. For these rules, select a bundle with `xlsynth_driver_version =
"0.83.0"` and `xls_version = "0.62.0"`. Use the registered bundle or set
`xls_bundle` on a target. The `bx_to_sv` macro uses the same
bundle for both steps.

```starlark
load("@rules_xlsynth//:rules.bzl", "block_ir_to_sv", "bx_library", "bx_to_ir", "bx_to_sv", "dslx_library")

bx_library(
    name = "counter_cells",
    srcs = ["counter_cells.bx"],
)

dslx_library(
    name = "counter_math",
    srcs = ["counter_math.x"],
)

bx_library(
    name = "counter_bx",
    srcs = ["counter.bx"],
    deps = [":counter_cells"],
    dslx_deps = [":counter_math"],
)

bx_to_sv(
    name = "counter_rtl",
    lib = ":counter_bx",
    top = "counter",
)

bx_to_ir(
    name = "counter_ir",
    lib = ":counter_bx",
    top = "counter",
)

block_ir_to_sv(
    name = "counter_named_rtl",
    ir = ":counter_ir",
    lower_ir = True,
    module_name = "my_counter",
)
```

Set `root` to one of the direct `srcs` for a multi-source `bx_library`.
Libraries carry the root and transitive sources in `BxInfo`. They may contain
generic blocks, functions, or types, and the driver checks imported
declarations during design compilation. The rules pass explicit toolchain
import paths followed by the roots of the declared source files. Builds stage
the declared sources in the same layout used by test runfiles. An explicit
`external/<repository>` path into a declared external repository resolves to
`../<repository>` in that layout. Use paths qualified from a repository root
for imports across packages.

`bx_to_ir` produces `<name>.block.ir` and exports `BlockIrInfo` with the
selected top. Set `link_ir` to one IR package providing the implementations
for BX `extern fn` and `extern block` declarations. A `dslx_to_ir` target
supplies its unoptimized package. `reset_active_low` and
`reset_asynchronous` default to `False` and apply to the hierarchy.
`warnings_as_errors` defaults to `True`. `bx_to_sv` also accepts these
attributes.

`block_ir_to_sv` emits `<name>.sv` with the top module and its instantiated
modules using the driver's default RTL layout, which supports register
feedback. It accepts a single package-form `.ir` file. Supply `top` if the
package has no marked top block. Set `lower_ir = True` to inline function calls
and maps and unroll counted loops before emission. `bx_to_sv` enables this
lowering by default.

### `bx_to_gv` - map BX to a gate-level netlist

`bx_to_gv` accepts the same compilation attributes as `bx_to_ir` and
produces `<name>.gv` using the driver's native mapper. The required
`liberty_proto` input is a normalized Liberty library with the cells the
design needs. The mapper supports register enables and synchronous resets.
Use `bx_to_sv` to emit RTL with asynchronous resets.

```starlark
load("@rules_xlsynth//:rules.bzl", "bx_to_gv")

bx_to_gv(
    name = "counter_mapped",
    lib = ":counter_bx",
    top = "counter",
    liberty_proto = "cells.textproto",
)
```

### Run and prove BX properties

`bx_test` runs `#[test]` functions and blocks and samples clocked
`#[quickcheck]` and `#[invariant]` blocks. Set `quickcheck_trials`,
`invariant_cycles`, and `seed` to control and reproduce sampling. Pass
`seed` as a decimal string to cover the full unsigned 64-bit range. Set
`cross_check_vastly = True` to compare samples against generated RTL.

`bx_prove_quickcheck_test` proves each clocked QuickCheck over its declared
tick schedule, for all legal stimulus and initial DUT state.
`bx_prove_invariant_test` checks invariants and their lemmas with k-induction
from the declared initialization. Set `max_depth` to cap the induction
depth or set `mode = "bmc"` to check a prefix of that many cycles. Both
proof rules support `time_limit_ms` per solver query and require a
Bitwuzla-enabled driver. Disproved and inconclusive properties fail the
Bazel test, with diagnostics in the test log.

These rules run declarations in the root file of `lib`. Imports supply
dependencies. All three accept `link_ir`, `warnings_as_errors`,
`reset_active_low`, and `xls_bundle`, and use synchronous reset.

```starlark
load("@rules_xlsynth//:rules.bzl", "bx_prove_invariant_test", "bx_prove_quickcheck_test", "bx_test")

bx_test(
    name = "counter_bx_test",
    lib = ":counter_bx",
    quickcheck_trials = 200,
    seed = "42",
)

bx_prove_quickcheck_test(
    name = "counter_quickcheck_proof_test",
    lib = ":counter_bx",
    time_limit_ms = 30000,
)

bx_prove_invariant_test(
    name = "counter_invariant_proof_test",
    lib = ":counter_bx",
    max_depth = 8,
)
```

Run `bazel test //sample_bx/...` to build and verify the hierarchical BX
accumulator and mapped inverter. The accumulator QuickCheck exercises reset,
update, and hold with the Vastly RTL cross-check enabled.

### `ir_to_delay_info` - convert IR to delay info

```starlark
load("@rules_xlsynth//:rules.bzl", "ir_to_delay_info")

ir_to_delay_info(
    name = "my_dslx_library_delay_info",
    ir = ":my_dslx_library_ir",
    delay_model = "asap7",
    top = "main",
)
```

### `dslx_prove_quickcheck_test` - prove quickcheck holds for entire input domain

Runs `xlsynth-driver prove-quickcheck --solver bitwuzla` using the selected
toolchain or explicit `xls_bundle`. The driver must include Bitwuzla support;
download-backed bundles build it with `with-bitwuzla-system`. Cargo builds need
the system Bitwuzla development libraries, and dynamically linked drivers need
the matching libraries at runtime. Existing Bitwuzla-enabled installed drivers
are reused. There is no fallback to the native XLS/Z3 prover.

`top` is a full-match regular expression over QuickCheck function names. Omit
it to prove every QuickCheck in the library; selecting no properties fails.
Assertions must never fail (`--assertion-semantics never`). Bazel supplies its
default target-level test result; property diagnostics remain in the test log.
Under `bazel test`, the driver's JSON report is saved as the undeclared test
output `quickcheck.json`. The rule first runs the selected XLS typechecker to
enforce configured warning settings.
The rule adds no separate XLS IR optimization step; optimization follows the
selected driver's behavior (older releases use unoptimized IR). Proof runtimes
may differ from native XLS proving.

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_prove_quickcheck_test")

# Tests that we can prove the quickcheck holds for its entire input domain.
dslx_prove_quickcheck_test(
    name = "quickcheck_various_things_proof_test",
    lib = ":my_dslx_library",
    top = "quickcheck_various_things",
)
```

### `ir_prove_equiv_test` - prove two IR functions equivalent

Runs the selected driver's `ir-equiv` command for the `lhs`, `rhs`, and `top`
attributes. Under `bazel test`, it saves the driver's JSON report as the
undeclared test output `ir_equiv.json`, including `success` and `error_str`.
The report is available for both successful proofs and counterexamples; a
failure result alone is not evidence of non-equivalence because solver errors
and inconclusive results also fail.

### Lean equivalence tests for DSLX and XLS IR functions

Use `dslx_lean_equiv_test` to prove two DSLX functions return equal results for
every input. Supply a `dslx_library` and a top function name on each side. The
rule lowers and optimizes both functions with the registered XLS toolchain.

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_lean_equiv_test")

dslx_lean_equiv_test(
    name = "dslx_identity_test",
    lhs = ":identity_lib",
    lhs_top = "identity",
    rhs = ":reference_lib",
    rhs_top = "add_zero",
    proof = "Reflexivity.lean",
    proof_theorem = "Reflexivity.equivalent",
)
```

Use `ir_fn_lean_equiv_test` to start at the IR boundary. Its `lhs` and `rhs`
each accept a single `.ir` file or a `dslx_to_ir` target providing optimized
IR. The driver selects the package top or sole function on each side.
Set `lhs_top` or `rhs_top` to select another IR function. The argument and
result types must match.

Both rules generate the proposition `Target.Equivalent` from the selected
functions. Supply an ordinary Lean module that imports `Target`, and name
the theorem that proves the proposition. For the example above, the
optimizer reduces both functions to the identity, so the proof is:

```lean
import Target

theorem Reflexivity.equivalent : Target.Equivalent := by
  intro x
  rfl
```

List any additional local modules in `proof_srcs`. Their paths under the proof
file's directory determine their module names. The driver checks the compiled
proof against the generated proposition and audits its dependencies. The
default `allow_native_checks = True` permits replaying closed Boolean checks
using native evaluation. Set it to `False` to require a kernel-only proof
using at most Lean’s three standard axioms (`propext`, `Classical.choice` and
`Quot.sound`). In this mode the test also requires the verifier to report zero
native checks.

Configure the proof toolchain in `MODULE.bazel`. For example:

```starlark
xls.toolchain(
    name = "proof_xls",
    artifact_source = "download_only",
    xls_version = "0.62.0",
    xlsynth_driver_version = "0.83.0",
    lean_artifact_source = "download_only",
    lean_version = "4.34.1",
)
use_repo(xls, "proof_xls_toolchain")
```

Register that toolchain, or set `xls_bundle = "@proof_xls_toolchain//:bundle"`
on the test to select the proof driver and Lean independently of DSLX lowering.
The driver must provide `ir-fn-lean-prepare` and `ir-fn-lean-check`.

Lean is optional for other rules. Its artifact source can be configured
independently of XLS. With `download_only`, Bazel verifies the official
release archive against a pinned SHA-256. Checksums are included for Lean
4.34.1 on Linux and macOS, on x86-64 and AArch64. To use an installation,
set `installed_lean_root_prefix` and `lean_version`. The default
`installed_only` source selects `<installed_lean_root_prefix>/<lean_version>`.
The `auto` source checks the same location first and falls back to the pinned
download. The distribution must include `bin/lean`, `bin/cadical`,
`lib/lean` and `src/lean`.

Run the [examples](testdata/ir_fn_lean_equiv/BUILD.bazel) from this
repository with:

```sh
bazel test //testdata/ir_fn_lean_equiv:dslx_identity_test //testdata/ir_fn_lean_equiv:identity_test
```

The test writes `ir_fn_lean_equiv.json` to Bazel's undeclared test outputs.
The report includes the audit result and, for drivers supporting it, the
`native_checks_replayed` count. To inspect the generated proposition and
Lean functions, build the test with `--output_groups=lean_target`.

### `ir_to_gates` - convert IR to gate-level analysis

Given an IR target (typically from `dslx_to_ir`) as input via `ir_src`, this rule runs the `ir2gates` tool to produce a text file containing gate-level analysis (e.g., gate counts, depth).

```starlark
load("@rules_xlsynth//:rules.bzl", "ir_to_gates")

ir_to_gates(
    name = "my_ir_gates_analysis",
    ir_src = ":my_dslx_library_ir",  # Target providing IrInfo
)
```

When the gate graph is large the "FRAIGing" optimization process can be slow, so there is a boolean option on the rule that allows users to disable it.

```starlark
load("@rules_xlsynth//:rules.bzl", "ir_to_gates")

ir_to_gates(
    name = "my_ir_gates_analysis_nofraig",
    ir_src = ":my_dslx_library_ir",
    fraig = False,
)
```

### `dslx_stitch_pipeline` - stitch pipeline stage functions

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_stitch_pipeline")

dslx_stitch_pipeline(
    name = "my_pipeline",
    lib = ":my_dslx_library",
    top = "foo",
)
```

#### Attributes (non-exhaustive)

* `stages` - optional explicit list of stage function names to stitch when auto-discovery is not desired.
* `input_valid_signal` / `output_valid_signal` - when provided, additional `valid` handshaking logic is generated.
* `reset` - name of the reset signal to thread through the generated wrapper. Use together with `reset_active_low` to control polarity.
* `reset_active_low` - `True` when the reset signal is active low (defaults to `False`).
* `flop_inputs` - `True` to insert an input register stage in front of the first stitched stage (defaults to `True`).
* `flop_outputs` - `True` to insert an output register stage after the final stage (defaults to `True`).

The `flop_inputs` and `flop_outputs` flags give fine-grained control over where pipeline registers are placed. For example, the `sample/BUILD.bazel` file contains demonstrations that verify:

* `flop_inputs = True,  flop_outputs = False` - only input side flops.
* `flop_inputs = False, flop_outputs = True` - only output side flops.

Corresponding golden SystemVerilog files live next to the BUILD file so you can observe the emitted RTL.
