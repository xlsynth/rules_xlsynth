# `rules_xlsynth`

[![CI](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml)

### `dslx_library`, `dslx_test` — libraries/tests for DSLX files

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_library", "dslx_test")

dslx_library(
    name = "foo",
    srcs = ["foo.x"],
)

# `dslx_test` can run all the inline tests in an associated library.
dslx_test(
    name = "foo_test",
    deps = [":foo"],
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
    name = "foo_pkg",
    deps = [":foo"],
)
```
