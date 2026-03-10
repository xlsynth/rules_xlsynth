load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

_XLS_TOOLCHAIN_TYPE = "//:toolchain_type"
_TRI_STATE_VALUES = ["", "true", "false"]

def _split_nonempty(value, separator):
    if not value:
        return []
    items = []
    for item in value.split(separator):
        stripped = item.strip()
        if stripped:
            items.append(stripped)
    return items

def _validate_tri_state(value, label):
    if value not in _TRI_STATE_VALUES:
        fail("{} must be one of {}".format(label, _TRI_STATE_VALUES))
    return value

def _xls_toolchain_impl(ctx):
    tools_path = ctx.attr._tools_path_flag[BuildSettingInfo].value
    dslx_stdlib_path = ctx.attr._dslx_stdlib_path_flag[BuildSettingInfo].value
    if not dslx_stdlib_path and tools_path:
        dslx_stdlib_path = tools_path + "/xls/dslx/stdlib"

    type_inference_v2 = _validate_tri_state(
        ctx.attr._type_inference_v2_flag[BuildSettingInfo].value,
        "@rules_xlsynth//config:type_inference_v2",
    )
    use_system_verilog = _validate_tri_state(
        ctx.attr._use_system_verilog_flag[BuildSettingInfo].value,
        "@rules_xlsynth//config:use_system_verilog",
    )
    add_invariant_assertions = _validate_tri_state(
        ctx.attr._add_invariant_assertions_flag[BuildSettingInfo].value,
        "@rules_xlsynth//config:add_invariant_assertions",
    )

    return [platform_common.ToolchainInfo(
        driver_path = ctx.attr._driver_path_flag[BuildSettingInfo].value,
        tools_path = tools_path,
        dslx_stdlib_path = dslx_stdlib_path,
        runtime_library_path = ctx.attr._runtime_library_path_flag[BuildSettingInfo].value,
        driver_supports_sv_enum_case_naming_policy = ctx.attr._driver_supports_sv_enum_case_naming_policy_flag[BuildSettingInfo].value,
        dslx_path = _split_nonempty(ctx.attr._dslx_path_flag[BuildSettingInfo].value, ":"),
        enable_warnings = _split_nonempty(ctx.attr._enable_warnings_flag[BuildSettingInfo].value, ","),
        disable_warnings = _split_nonempty(ctx.attr._disable_warnings_flag[BuildSettingInfo].value, ","),
        type_inference_v2 = type_inference_v2,
        gate_format = ctx.attr._gate_format_flag[BuildSettingInfo].value,
        assert_format = ctx.attr._assert_format_flag[BuildSettingInfo].value,
        use_system_verilog = use_system_verilog,
        add_invariant_assertions = add_invariant_assertions,
    )]

xls_toolchain = rule(
    implementation = _xls_toolchain_impl,
    attrs = {
        "_driver_path_flag": attr.label(default = "//config:driver_path"),
        "_driver_supports_sv_enum_case_naming_policy_flag": attr.label(default = "//config:driver_supports_sv_enum_case_naming_policy"),
        "_tools_path_flag": attr.label(default = "//config:tools_path"),
        "_dslx_stdlib_path_flag": attr.label(default = "//config:dslx_stdlib_path"),
        "_runtime_library_path_flag": attr.label(default = "//config:runtime_library_path"),
        "_dslx_path_flag": attr.label(default = "//config:dslx_path"),
        "_enable_warnings_flag": attr.label(default = "//config:enable_warnings"),
        "_disable_warnings_flag": attr.label(default = "//config:disable_warnings"),
        "_type_inference_v2_flag": attr.label(default = "//config:type_inference_v2"),
        "_gate_format_flag": attr.label(default = "//config:gate_format"),
        "_assert_format_flag": attr.label(default = "//config:assert_format"),
        "_use_system_verilog_flag": attr.label(default = "//config:use_system_verilog"),
        "_add_invariant_assertions_flag": attr.label(default = "//config:add_invariant_assertions"),
    },
)

def get_xls_toolchain(ctx):
    return ctx.toolchains[_XLS_TOOLCHAIN_TYPE]

def require_driver_toolchain(ctx):
    toolchain = get_xls_toolchain(ctx)
    if not toolchain.driver_path:
        fail("rules_xlsynth requires @rules_xlsynth//config:driver_path to be set")
    _require_common_toolchain(toolchain)
    return toolchain

def require_tools_toolchain(ctx):
    toolchain = get_xls_toolchain(ctx)
    _require_common_toolchain(toolchain)
    return toolchain

def _require_common_toolchain(toolchain):
    if not toolchain.tools_path:
        fail("rules_xlsynth requires @rules_xlsynth//config:tools_path to be set")
    if not toolchain.dslx_stdlib_path:
        fail("rules_xlsynth requires @rules_xlsynth//config:dslx_stdlib_path to be set or derivable from tools_path")

def _toml_quote(value):
    return "\"{}\"".format(value.replace("\\", "\\\\").replace("\"", "\\\""))

def _toml_array(values):
    return "[{}]".format(", ".join([_toml_quote(value) for value in values]))

def _resolve_tri_state(default_value, override_value):
    if override_value == "":
        return default_value
    return override_value

def declare_xls_toolchain_toml(
        ctx,
        *,
        name,
        type_inference_v2 = "",
        gate_format = None,
        assert_format = None,
        use_system_verilog = "",
        add_invariant_assertions = "",
        array_index_bounds_checking = ""):
    toolchain = require_tools_toolchain(ctx)

    resolved_type_inference_v2 = _resolve_tri_state(toolchain.type_inference_v2, type_inference_v2)
    resolved_use_system_verilog = _resolve_tri_state(toolchain.use_system_verilog, use_system_verilog)
    resolved_add_invariant_assertions = _resolve_tri_state(toolchain.add_invariant_assertions, add_invariant_assertions)
    resolved_gate_format = toolchain.gate_format if gate_format == None else gate_format
    resolved_assert_format = toolchain.assert_format if assert_format == None else assert_format

    lines = [
        "[toolchain]",
        "tool_path = {}".format(_toml_quote(toolchain.tools_path)),
        "",
        "[toolchain.dslx]",
        "dslx_stdlib_path = {}".format(_toml_quote(toolchain.dslx_stdlib_path)),
        "dslx_path = {}".format(_toml_array(toolchain.dslx_path)),
        "enable_warnings = {}".format(_toml_array(toolchain.enable_warnings)),
        "disable_warnings = {}".format(_toml_array(toolchain.disable_warnings)),
    ]
    if resolved_type_inference_v2:
        lines.append("type_inference_v2 = {}".format(resolved_type_inference_v2))

    lines.extend([
        "",
        "[toolchain.codegen]",
    ])
    if resolved_gate_format:
        lines.append("gate_format = {}".format(_toml_quote(resolved_gate_format)))
    if resolved_assert_format:
        lines.append("assert_format = {}".format(_toml_quote(resolved_assert_format)))
    if resolved_use_system_verilog:
        lines.append("use_system_verilog = {}".format(resolved_use_system_verilog))
    if resolved_add_invariant_assertions:
        lines.append("add_invariant_assertions = {}".format(resolved_add_invariant_assertions))
    if array_index_bounds_checking:
        lines.append("array_index_bounds_checking = {}".format(array_index_bounds_checking))

    toolchain_toml = ctx.actions.declare_file("{}_{}.toml".format(ctx.label.name, name))
    ctx.actions.write(
        output = toolchain_toml,
        content = "\n".join(lines) + "\n",
    )
    return toolchain_toml
