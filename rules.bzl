load(
    ":dslx_provider.bzl",
    _DslxInfo = "DslxInfo",
    _dslx_library = "dslx_library",
)
load(
    ":dslx_test.bzl",
    _dslx_test = "dslx_test",
)

DslxInfo = _DslxInfo
dslx_library = _dslx_library
dslx_test = _dslx_test
