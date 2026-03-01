# `rules_xlsynth`

[![CI](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml)

### Workspace toolchains

`rules_xlsynth` now selects XLS artifacts from `MODULE.bazel` through the `xls`
module extension. A workspace instantiates one or more named bundles with
`xls.toolchain(...)`, exposes them with `use_repo(...)`, and registers one
default bundle with `register_toolchains("@<name>//:all")`.

```starlark
bazel_dep(name = "rules_xlsynth", version = "<release>")

xls = use_extension("@rules_xlsynth//:extensions.bzl", "xls")

xls.toolchain(
    name = "workspace_xls",
    xls_version = "0.38.0",
    xlsynth_driver_version = "0.33.0",
    artifact_source = "auto",
)

xls.toolchain(
    name = "legacy_xls",
    xls_version = "0.37.0",
    xlsynth_driver_version = "0.32.0",
    artifact_source = "download_only",
)

use_repo(xls, "workspace_xls", "legacy_xls")
register_toolchains("@workspace_xls//:all")
```

`artifact_source` chooses how each bundle repo is materialized:

- `auto` uses the exact versioned `/eda-tools` install when it exists and
  otherwise downloads the release artifacts.
- `eda_tools_only` requires the exact versioned `/eda-tools` install.
- `download_only` always downloads the release artifacts.
- `local_paths` uses `local_tools_path`, `local_dslx_stdlib_path`,
  `local_driver_path`, and `local_libxls_path`.

The attributes accepted by each mode are strict:

- `local_paths` requires all four `local_*` attrs and does not accept
  `xls_version` or `xlsynth_driver_version`.
- `auto`, `eda_tools_only`, and `download_only` require both
  `xls_version` and `xlsynth_driver_version` and do not accept any `local_*`
  attrs.

Download-backed modes also have one host prerequisite: when `auto` falls back
to downloading, or when `download_only` is selected, the repository rule
installs `xlsynth-driver` with `rustup run nightly cargo install`. That means
the host running module resolution must have `rustup` available with a nightly
toolchain installed.

Each `xls.toolchain(...)` call exports a small repo surface:

- `@<name>//:all` for `register_toolchains(...)`
- `@<name>//:bundle` for explicit `xls_bundle` overrides
- `@<name>//:libxls` and `@<name>//:libxls_link` for native consumers
- `@<name>//:dslx_stdlib` for packages that need the standard library tree

Supported leaf rules may opt out of the registered default bundle with
`xls_bundle = "@<name>//:bundle"`. Today that escape hatch is available on
`dslx_to_sv_types`, `dslx_to_pipeline`, `dslx_to_pipeline_eco`, and
`dslx_stitch_pipeline`.

```starlark
dslx_to_pipeline(
    name = "legacy_pipeline",
    delay_model = "asap7",
    pipeline_stages = 1,
    top = "main",
    deps = [":my_dslx_library"],
    xls_bundle = "@legacy_xls//:bundle",
)
```

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
)
```

`sv_enum_case_naming_policy` is required. Allowed values (matching
`xlsynth-driver`) are `unqualified` and `enum_qualified`.

The selected bundle records whether its `xlsynth-driver` supports the
`--sv_enum_case_naming_policy` CLI flag. Older bundles still work with
`sv_enum_case_naming_policy = "unqualified"`; `enum_qualified` only works when
the chosen workspace bundle or explicit `xls_bundle` advertises support.

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

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_prove_quickcheck_test")

# Tests that we can prove the quickcheck holds for its entire input domain.
dslx_prove_quickcheck_test(
    name = "quickcheck_various_things_proof_test",
    lib = ":my_dslx_library",
    top = "quickcheck_various_things",
)
```

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
