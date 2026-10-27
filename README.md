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

Lean proof rules use an optional Lean distribution configured on the same
toolchain. For example, Bazel can download a pinned official release:

```starlark
xls.toolchain(
    name = "workspace_xls",
    # Existing XLS artifact configuration...
    lean_artifact_source = "download_only",
    lean_version = "4.34.1",
)
```

`lean_artifact_source` is independent of the XLS `artifact_source` setting:

- `download_only` downloads the official platform archive from the
  `leanprover/lean4` GitHub release and verifies a checked-in SHA-256 digest.
  It does not accept `installed_lean_root_prefix`.
- `installed_only` requires `installed_lean_root_prefix` and selects
  `<installed_lean_root_prefix>/<lean_version>`.
- `auto` requires the same prefix, uses the installed distribution when its
  required files exist, and otherwise downloads the same pinned version.

Omitting `lean_artifact_source` retains `installed_only` behavior. Omitting all
Lean attributes leaves Lean unavailable to proof rules. Download checksums are
currently registered for Lean 4.34.1 on Linux and macOS, for x86-64 and AArch64.
Bazel caches downloaded archives by checksum. Resolving a configured Lean
repository may fetch the archive before a proof action runs.

The distribution must contain `bin/lean`, `bin/cadical`, `lib/lean`, and
`src/lean`. The materialization action checks Lean's reported version and
preserves the required layout in a declared tree artifact. The test invokes
Lean directly, without Elan or a PATH fallback. The existing resolved XLS
identity does not include Lean; downloaded Lean integrity comes from the pinned
archive checksum.

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
- XLS `download_only` does not accept `installed_tools_root_prefix` or
  `installed_driver_root_prefix`; Lean selection is independent.

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

### `netlist_lean_equiv_test` - check a supplied Lean proof of netlist equivalence

Mechanically converts two Liberty-backed mapped Verilog netlists into g8r
graphs and Lean circuits, then runs a supplied proof of their equivalence.
The selected `xls.toolchain` must configure Lean as described above,
and its driver must provide `gv2g8r`, `g8r-lean-prepare`, and
`g8r-lean-check`.

```starlark
load("@rules_xlsynth//:rules.bzl", "netlist_lean_equiv_test")

netlist_lean_equiv_test(
    name = "adder_equiv_test",
    lhs = ":reference_netlist",
    lhs_sha256 = "<64-character SHA-256>",
    rhs = ":optimized_netlist",
    rhs_sha256 = "<64-character SHA-256>",
    liberty_proto = ":cells_liberty_proto",
    lhs_top = "adder",
    rhs_top = "adder",
    proof = "proof/Body.lean",
)
```

`lhs` and `rhs` each provide exactly one netlist file. Workspace files,
generated outputs, and external-repository files are accepted. The single
`liberty_proto` is used for both sides. The hash attributes are SHA-256 over
the exact file contents, decompressed first for `.gz` inputs. Whitespace and
comments count. A build action verifies each hash before conversion and writes
the exact verified bytes consumed by `gv2g8r`. A mismatch reports the side,
expected hash, and actual hash.

Optional extraction attributes are:

- `lhs_top`, `rhs_top`: module selection; omit when unambiguous.
- `lhs_cone_boundary_file`, `rhs_cone_boundary_file`: the driver's compact JSON
  source/sink boundary files. Omission selects the complete module interface.
- `collapse_sequential`: collapse reached pipeline registers; default `False`.
- `collapse_load_enable_feedback`: collapse recognized load-enable feedback
  with zero prior state; default `False` and requires `collapse_sequential`.

The initial rule checks combinational `GateFn` equivalence. Reached residual
state is rejected. Extracted input and output ports must have matching names
and widths in the same order.

The build creates the two `.g8r` graphs and a Lean target directory containing
`Lhs.aag`, `Rhs.aag`, shared support modules, `Target.lean`, and `Check.lean`.
`Target.lean` embeds both AAG files through the shared loader and defines their
equivalence proposition. Inspect that directory while developing a proof with:

```shell
bazel build //path:adder_equiv_test --output_groups=lean_target
```

The `proof` file contains a complete Lean term for `Target.Equivalent`, such as
a `by` tactic block or a helper theorem name. The runner generates the imports
and `UserProof.equivalent` theorem declaration. Optional `proof_srcs` supplies
helper `.lean` files, all of which are imported mechanically. Helpers must be
under the body's directory; their relative paths are preserved. Lean discovers
helper dependencies and compiles them in dependency order. The runner invokes
Lean directly; `bv_decide` uses Lean's bundled solver lookup.

Under `bazel test`, the rule writes `netlist_lean_equiv.json` to the undeclared
test outputs with status, versions, hashes, extraction settings, timing, and
Lean diagnostics. Success means Lean accepted the generated root theorem under
its ordinary rules. Proof auditing is not performed, and the report records
`audit_performed: false`.

The checked-in proof targets are:

- `basic`: plain netlists and [`Proof/Body.lean`](testdata/netlist_lean_equiv/Proof/Body.lean).
- `equivalent`: the same proof with a generated gzip-compressed RHS netlist.
- `pipeline`: selected cone boundaries and pipeline/load-enable collapsing.
- `with_helpers`: `Proof/WithHelpers.lean` and two helper modules exercising
  dependency ordering and `bv_decide`.

With a selected toolchain that provides the required driver commands and Lean,
run them directly:

```shell
bazel test \
  //testdata/netlist_lean_equiv:basic \
  //testdata/netlist_lean_equiv:equivalent \
  //testdata/netlist_lean_equiv:pipeline \
  //testdata/netlist_lean_equiv:with_helpers
```

These targets are tagged `manual` while the repository's released self-test
driver predates the Lean commands.

Expected rejections and toolchain configuration are separate Bazel `py_test`
targets:

- `netlist_lean_equiv_rejects_sha256_mismatch_and_inequivalent_netlists_test`
  checks that a wrong digest and an inequivalent RHS are rejected for the
  expected reasons.
- `netlist_lean_equiv_toolchain_configuration_test` uses `basic` to check
  installed Lean, downloads, `auto` fallback, and missing configuration errors.

These manual local tests invoke Bazel in temporary workspaces and inherit the
existing local tool-path variables. Run both with:

```shell
RULES_XLSYNTH_TEST_DRIVER=/path/to/xlsynth-driver \
RULES_XLSYNTH_TEST_XLS_ROOT=/path/to/xls-release \
RULES_XLSYNTH_TEST_LEAN_ROOT=/path/to/lean-4.34.1 \
bazel test --nocache_test_results \
  //:netlist_lean_equiv_rejects_sha256_mismatch_and_inequivalent_netlists_test \
  //:netlist_lean_equiv_toolchain_configuration_test
```

Use `--nocache_test_results` when validating rebuilt binaries at the same local
paths.

`RULES_XLSYNTH_TEST_BAZEL` and `RULES_XLSYNTH_TEST_BAZEL_STARTUP_OPTIONS` may
select the nested Bazel executable and startup options. If the required tool
paths are absent, the tests retain their existing skipped result. The same
Python file can still run both cases directly with
`python3 netlist_lean_equiv_integration_test.py` and the same environment.

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
