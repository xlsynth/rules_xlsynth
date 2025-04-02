load(
    ":dslx_fmt.bzl",
    _dslx_fmt_test = "dslx_fmt_test",
)
load(
    ":dslx_prove_quickcheck_test.bzl",
    _dslx_prove_quickcheck_test = "dslx_prove_quickcheck_test",
)
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
    ":dslx_to_ir.bzl",
    _dslx_to_ir = "dslx_to_ir",
)
load(
    ":dslx_to_pipeline.bzl",
    _dslx_to_pipeline = "dslx_to_pipeline",
)
load(
    ":dslx_to_sv_types.bzl",
    _dslx_to_sv_types = "dslx_to_sv_types",
)
load(":helpers.bzl", _mangle_dslx_name = "mangle_dslx_name")
load(":ir_prove_equiv_test.bzl", _ir_prove_equiv_test = "ir_prove_equiv_test")
load(
    ":ir_to_delay_info.bzl",
    _ir_to_delay_info = "ir_to_delay_info",
)

DslxInfo = _DslxInfo
dslx_library = _dslx_library
dslx_test = _dslx_test
dslx_fmt_test = _dslx_fmt_test
dslx_to_sv_types = _dslx_to_sv_types
dslx_to_pipeline = _dslx_to_pipeline
dslx_to_ir = _dslx_to_ir
ir_to_delay_info = _ir_to_delay_info
mangle_dslx_name = _mangle_dslx_name
dslx_prove_quickcheck_test = _dslx_prove_quickcheck_test
ir_prove_equiv_test = _ir_prove_equiv_test
