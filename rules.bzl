load(
    ":dslx_provider.bzl",
    _DslxInfo = "DslxInfo",
    _dslx_library = "dslx_library",
)
load(
    ":dslx_test.bzl",
    _dslx_test = "dslx_test",
)
load(
    ":dslx_fmt.bzl",
    _dslx_fmt_test = "dslx_fmt_test",
)
load(
    ":dslx_to_sv_types.bzl",
    _dslx_to_sv_types = "dslx_to_sv_types",
)
load(
    ":dslx_to_pipeline.bzl",
    _dslx_to_pipeline = "dslx_to_pipeline",
)
load(
    ":dslx_to_ir.bzl",
    _dslx_to_ir = "dslx_to_ir",
)

DslxInfo = _DslxInfo
dslx_library = _dslx_library
dslx_test = _dslx_test
dslx_fmt_test = _dslx_fmt_test
dslx_to_sv_types = _dslx_to_sv_types
dslx_to_pipeline = _dslx_to_pipeline
dslx_to_ir = _dslx_to_ir
