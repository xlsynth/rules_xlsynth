# `rules_xlsynth`

[![CI](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/xlsynth/rules_xlsynth/actions/workflows/ci.yml)

### `dslx_library`, `dslx_test` -- libraries/tests for DSLX files

```
load("@rules_xlsynth//:rules.bzl", "dslx_library", "dslx_test")

dslx_library(
    name = "imported",
    srcs = ["imported.x"],
)

# `dslx_test` can run all the inline tests in an associated library.
dslx_test(
    name = "imported_test",
    deps = [":imported"],
)
```

### `dslx_fmt_test` -- format DSLX files

```starlark
load("@rules_xlsynth//:rules.bzl", "dslx_fmt_test")

dslx_fmt_test(
    name = "dslx_fmt_test",
    srcs = glob(["*.x"]),
)
```
