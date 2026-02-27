# `rules_xlsynth`

[![CI](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml)

### Toolchain configuration

`rules_xlsynth` registers a default Bazel toolchain that reads its values from
typed Bazel build settings under `@rules_xlsynth//config`. The rules then
generate a declared `xlsynth-toolchain.toml` input for each action instead of
reading XLS configuration from the action environment.

The most important build settings are:

- `@rules_xlsynth//config:driver_path`
- `@rules_xlsynth//config:driver_supports_sv_enum_case_naming_policy`
- `@rules_xlsynth//config:tools_path`
- `@rules_xlsynth//config:runtime_library_path`
- `@rules_xlsynth//config:dslx_stdlib_path`
- `@rules_xlsynth//config:dslx_path`
- `@rules_xlsynth//config:enable_warnings`
- `@rules_xlsynth//config:disable_warnings`
- `@rules_xlsynth//config:type_inference_v2`
- `@rules_xlsynth//config:gate_format`
- `@rules_xlsynth//config:assert_format`
- `@rules_xlsynth//config:use_system_verilog`
- `@rules_xlsynth//config:add_invariant_assertions`

These can be set in `.bazelrc` like this:

```
build --@rules_xlsynth//config:driver_path=/path/to/xlsynth-driver
build --@rules_xlsynth//config:driver_supports_sv_enum_case_naming_policy=true
build --@rules_xlsynth//config:tools_path=/path/to/xlsynth/tools
build --@rules_xlsynth//config:runtime_library_path=/path/to/libxls/dir
build --@rules_xlsynth//config:dslx_stdlib_path=/path/to/xls/dslx/stdlib
build --@rules_xlsynth//config:dslx_path=path/to/additional/dslx/files:another/path
build --@rules_xlsynth//config:enable_warnings=warning1,warning2
build --@rules_xlsynth//config:disable_warnings=warning3,warning4
```

`dslx_stdlib_path` is optional when `tools_path` already points at an extracted
XLS release tree with `xls/dslx/stdlib` underneath it.

Or by passing the same flags directly on the Bazel command line.

### `dslx_library`, `dslx_test` — libraries/tests for DSLX files

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

### `dslx_fmt_test` — format DSLX files

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_fmt_test")

dslx_fmt_test(
    name = "dslx_fmt_test",
    srcs = glob(["*.x"]),
)
```

### `dslx_to_sv_types` — create `_pkg.sv` file

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

When the configured driver is new enough to accept the
`--sv_enum_case_naming_policy` CLI flag, set
`--@rules_xlsynth//config:driver_supports_sv_enum_case_naming_policy=true`.
Older drivers still work with `sv_enum_case_naming_policy = "unqualified"`;
the rule omits the flag in that compatibility mode and rejects
`enum_qualified` explicitly.

### `dslx_to_ir` — convert DSLX to optimized IR

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

### `ir_to_delay_info` — convert IR to delay info

```starlark
load("@rules_xlsynth//:rules.bzl", "ir_to_delay_info")

ir_to_delay_info(
    name = "my_dslx_library_delay_info",
    ir = ":my_dslx_library_ir",
    delay_model = "asap7",
    top = "main",
)
```

### `dslx_prove_quickcheck_test` — prove quickcheck holds for entire input domain

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_prove_quickcheck_test")

# Tests that we can prove the quickcheck holds for its entire input domain.
dslx_prove_quickcheck_test(
    name = "quickcheck_various_things_proof_test",
    lib = ":my_dslx_library",
    top = "quickcheck_various_things",
)
```

### `ir_to_gates` — convert IR to gate-level analysis

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

### `dslx_stitch_pipeline` — stitch pipeline stage functions

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_stitch_pipeline")

dslx_stitch_pipeline(
    name = "my_pipeline",
    lib = ":my_dslx_library",
    top = "foo",
)
```

#### Attributes (non-exhaustive)

* `stages` — optional explicit list of stage function names to stitch when auto-discovery is not desired.
* `input_valid_signal` / `output_valid_signal` — when provided, additional `valid` handshaking logic is generated.
* `reset` — name of the reset signal to thread through the generated wrapper. Use together with `reset_active_low` to control polarity.
* `reset_active_low` — `True` when the reset signal is active low (defaults to `False`).
* `flop_inputs` — `True` to insert an input register stage in front of the first stitched stage (defaults to `True`).
* `flop_outputs` — `True` to insert an output register stage after the final stage (defaults to `True`).

The `flop_inputs` and `flop_outputs` flags give fine-grained control over where pipeline registers are placed. For example, the `sample/BUILD.bazel` file contains demonstrations that verify:

* `flop_inputs = True,  flop_outputs = False` — only input side flops.
* `flop_inputs = False, flop_outputs = True` — only output side flops.

Corresponding golden SystemVerilog files live next to the BUILD file so you can observe the emitted RTL.
