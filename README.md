# `rules_xlsynth`

[![CI](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml)

### `.bazelrc`-settable configuration

These environment variables can act as a repository-level configuration for the `rules_xlsynth` rules:

- `XLSYNTH_DRIVER_DIR`: the path to the `xlsynth-driver` directory, i.e. containing the
  `xlsynth-driver` binary (which can be installed via `cargo` from its Rust crate). Note that this
  is named with a `_DIR` suffix because that differentiates it from a direct path to the binary.
- `XLSYNTH_TOOLS`: the path to the xlsynth tool directory, i.e. containing tools from releases
  such as `dslx_interpreter_main`, `ir_converter_main`, `codegen_main`, etc. (This can be used
  by the `xlsynth-driver` program instead of it directly calling `libxls` runtime APIs.)
- `XLSYNTH_DSLX_STDLIB_PATH`: the path to the DSLX stdlib to use. (Note that this refers to a
  directory that holds all the standard library files.)
- `XLSYNTH_DSLX_PATH`: a colon-separated list of additional DSLX paths to search for imported files.
- `XLSYNTH_DSLX_ENABLE_WARNINGS`: a comma-separated list of warnings to enable.
- `XLSYNTH_DSLX_DISABLE_WARNINGS`: a comma-separated list of warnings to disable.

These can be set in your `.bazelrc` file like this:

```
...
build --action_env XLSYNTH_DSLX_PATH="path/to/additional/dslx/files:another/path"
build --action_env XLSYNTH_DSLX_ENABLE_WARNINGS="warning1,warning2"
build --action_env XLSYNTH_DSLX_DISABLE_WARNINGS="warning3,warning4"
```

Or by passing `--action_env=` on the bazel command line.

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
)
```

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
