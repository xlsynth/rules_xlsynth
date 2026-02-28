load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain", "use_cpp_toolchain")
load("@rules_cc//cc:defs.bzl", "CcInfo", "cc_common")

_XLS_TOOLCHAIN_TYPE = "//:toolchain_type"
_TRI_STATE_VALUES = ["", "true", "false"]

XlsArtifactBundleInfo = provider(
    doc = "Versioned or local XLS bundle artifacts materialized by the module extension.",
    fields = {
        "artifact_inputs": "Declared files that must be present for actions using the bundle.",
        "driver": "The xlsynth-driver binary.",
        "driver_supports_sv_enum_case_naming_policy": "Whether the driver accepts --sv_enum_case_naming_policy.",
        "dslx_stdlib": "The DSLX stdlib root tree artifact.",
        "dslx_stdlib_path": "Directory path containing the DSLX stdlib sources.",
        "libxls": "The libxls shared library file.",
        "runtime_library_path": "Directory containing libxls for runtime loading.",
        "tools_root": "The XLS tool root tree artifact.",
        "tools_path": "Directory path containing the XLS tool binaries.",
    },
)


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


def _single_artifact(target, label):
    files = target[DefaultInfo].files.to_list()
    if len(files) != 1:
        fail("{} must provide exactly one artifact, got {}".format(label, len(files)))
    return files[0]


def _single_directory_artifact(target, label):
    files = target[DefaultInfo].files.to_list()
    if len(files) != 1:
        fail("{} must provide exactly one directory artifact, got {}".format(label, len(files)))
    artifact = files[0]
    if not artifact.is_directory:
        fail("{} must provide a directory artifact".format(label))
    return artifact


def _artifact_directory(files, label):
    if not files:
        fail("{} must provide at least one artifact".format(label))
    dirname = files[0].dirname
    for file in files[1:]:
        if file.dirname != dirname:
            fail("{} artifacts must share one directory; got {} and {}".format(label, dirname, file.dirname))
    return dirname


def _bundle_struct_from_provider(bundle):
    return struct(
        artifact_inputs = bundle.artifact_inputs,
        driver = bundle.driver,
        driver_path = bundle.driver.path,
        driver_supports_sv_enum_case_naming_policy = bundle.driver_supports_sv_enum_case_naming_policy,
        dslx_stdlib = bundle.dslx_stdlib,
        dslx_stdlib_path = bundle.dslx_stdlib_path,
        libxls = bundle.libxls,
        runtime_library_path = bundle.runtime_library_path,
        tools_root = bundle.tools_root,
        tools_path = bundle.tools_path,
    )


def _artifact_selection_from_flags(ctx):
    tools_path = ctx.attr._tools_path_flag[BuildSettingInfo].value
    dslx_stdlib_path = ctx.attr._dslx_stdlib_path_flag[BuildSettingInfo].value
    if not dslx_stdlib_path and tools_path:
        dslx_stdlib_path = tools_path + "/xls/dslx/stdlib"
    return struct(
        artifact_inputs = [],
        driver = None,
        driver_path = ctx.attr._driver_path_flag[BuildSettingInfo].value,
        driver_supports_sv_enum_case_naming_policy = ctx.attr._driver_supports_sv_enum_case_naming_policy_flag[BuildSettingInfo].value,
        dslx_stdlib = None,
        dslx_stdlib_path = dslx_stdlib_path,
        libxls = None,
        runtime_library_path = ctx.attr._runtime_library_path_flag[BuildSettingInfo].value,
        tools_root = None,
        tools_path = tools_path,
    )


def _toolchain_with_semantics(artifact_selection, ctx):
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
    return platform_common.ToolchainInfo(
        artifact_inputs = artifact_selection.artifact_inputs,
        driver = artifact_selection.driver,
        driver_path = artifact_selection.driver_path,
        tools_root = artifact_selection.tools_root,
        tools_path = artifact_selection.tools_path,
        dslx_stdlib = artifact_selection.dslx_stdlib,
        dslx_stdlib_path = artifact_selection.dslx_stdlib_path,
        libxls = artifact_selection.libxls,
        runtime_library_path = artifact_selection.runtime_library_path,
        driver_supports_sv_enum_case_naming_policy = artifact_selection.driver_supports_sv_enum_case_naming_policy,
        dslx_path = _split_nonempty(ctx.attr._dslx_path_flag[BuildSettingInfo].value, ":"),
        enable_warnings = _split_nonempty(ctx.attr._enable_warnings_flag[BuildSettingInfo].value, ","),
        disable_warnings = _split_nonempty(ctx.attr._disable_warnings_flag[BuildSettingInfo].value, ","),
        type_inference_v2 = type_inference_v2,
        gate_format = ctx.attr._gate_format_flag[BuildSettingInfo].value,
        assert_format = ctx.attr._assert_format_flag[BuildSettingInfo].value,
        use_system_verilog = use_system_verilog,
        add_invariant_assertions = add_invariant_assertions,
    )


def _xls_toolchain_impl(ctx):
    if ctx.attr.bundle:
        artifact_selection = _bundle_struct_from_provider(ctx.attr.bundle[XlsArtifactBundleInfo])
    else:
        artifact_selection = _artifact_selection_from_flags(ctx)
    return [_toolchain_with_semantics(artifact_selection, ctx)]


xls_toolchain = rule(
    implementation = _xls_toolchain_impl,
    attrs = {
        "bundle": attr.label(providers = [XlsArtifactBundleInfo]),
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


def _xls_bundle_impl(ctx):
    tool_files = ctx.attr.tools_root[DefaultInfo].files.to_list()
    dslx_stdlib = _single_directory_artifact(ctx.attr.dslx_stdlib, "dslx_stdlib")
    driver = _single_artifact(ctx.attr.driver, "driver")
    libxls = _single_artifact(ctx.attr.libxls, "libxls")
    artifact_inputs = tool_files + [dslx_stdlib, driver, libxls]
    tools_path = _artifact_directory(tool_files, "tools_root")
    return [
        XlsArtifactBundleInfo(
            artifact_inputs = artifact_inputs,
            driver = driver,
            driver_supports_sv_enum_case_naming_policy = ctx.attr.driver_supports_sv_enum_case_naming_policy,
            dslx_stdlib = dslx_stdlib,
            dslx_stdlib_path = dslx_stdlib.path,
            libxls = libxls,
            runtime_library_path = libxls.dirname,
            tools_root = tool_files[0],
            tools_path = tools_path,
        ),
        DefaultInfo(files = depset(direct = artifact_inputs)),
    ]


xls_bundle = rule(
    implementation = _xls_bundle_impl,
    attrs = {
        "driver": attr.label(allow_files = True, mandatory = True),
        "driver_supports_sv_enum_case_naming_policy": attr.bool(default = False),
        "dslx_stdlib": attr.label(mandatory = True),
        "libxls": attr.label(allow_files = True, mandatory = True),
        "tools_root": attr.label(mandatory = True),
    },
)


def get_xls_toolchain(ctx):
    return ctx.toolchains[_XLS_TOOLCHAIN_TYPE]


def _require_common_toolchain(toolchain):
    if not toolchain.tools_path:
        fail("rules_xlsynth requires a configured XLS tools root")
    if not toolchain.dslx_stdlib_path:
        fail("rules_xlsynth requires a configured DSLX stdlib root")


def _merge_toolchain_with_bundle(toolchain, bundle):
    artifact_selection = _bundle_struct_from_provider(bundle)
    return struct(
        artifact_inputs = artifact_selection.artifact_inputs,
        driver = artifact_selection.driver,
        driver_path = artifact_selection.driver_path,
        driver_supports_sv_enum_case_naming_policy = artifact_selection.driver_supports_sv_enum_case_naming_policy,
        dslx_stdlib = artifact_selection.dslx_stdlib,
        dslx_stdlib_path = artifact_selection.dslx_stdlib_path,
        libxls = artifact_selection.libxls,
        runtime_library_path = artifact_selection.runtime_library_path,
        tools_root = artifact_selection.tools_root,
        tools_path = artifact_selection.tools_path,
        dslx_path = toolchain.dslx_path,
        enable_warnings = toolchain.enable_warnings,
        disable_warnings = toolchain.disable_warnings,
        type_inference_v2 = toolchain.type_inference_v2,
        gate_format = toolchain.gate_format,
        assert_format = toolchain.assert_format,
        use_system_verilog = toolchain.use_system_verilog,
        add_invariant_assertions = toolchain.add_invariant_assertions,
    )


def require_driver_toolchain(ctx):
    toolchain = get_xls_toolchain(ctx)
    if not toolchain.driver_path:
        fail("rules_xlsynth requires a configured xlsynth-driver")
    _require_common_toolchain(toolchain)
    return toolchain


def require_tools_toolchain(ctx):
    toolchain = get_xls_toolchain(ctx)
    _require_common_toolchain(toolchain)
    return toolchain


def get_selected_tools_toolchain(ctx):
    toolchain = require_tools_toolchain(ctx)
    if hasattr(ctx.attr, "xls_bundle") and ctx.attr.xls_bundle:
        return _merge_toolchain_with_bundle(toolchain, ctx.attr.xls_bundle[XlsArtifactBundleInfo])
    return toolchain


def get_selected_driver_toolchain(ctx):
    toolchain = get_selected_tools_toolchain(ctx)
    if not toolchain.driver_path:
        fail("rules_xlsynth requires a configured xlsynth-driver")
    return toolchain


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
        toolchain = None,
        type_inference_v2 = "",
        gate_format = None,
        assert_format = None,
        use_system_verilog = "",
        add_invariant_assertions = "",
        array_index_bounds_checking = ""):
    resolved_toolchain = require_tools_toolchain(ctx) if toolchain == None else toolchain

    resolved_type_inference_v2 = _resolve_tri_state(resolved_toolchain.type_inference_v2, type_inference_v2)
    resolved_use_system_verilog = _resolve_tri_state(resolved_toolchain.use_system_verilog, use_system_verilog)
    resolved_add_invariant_assertions = _resolve_tri_state(resolved_toolchain.add_invariant_assertions, add_invariant_assertions)
    resolved_gate_format = resolved_toolchain.gate_format if gate_format == None else gate_format
    resolved_assert_format = resolved_toolchain.assert_format if assert_format == None else assert_format

    lines = [
        "[toolchain]",
        "tool_path = {}".format(_toml_quote(resolved_toolchain.tools_path)),
        "",
        "[toolchain.dslx]",
        "dslx_stdlib_path = {}".format(_toml_quote(resolved_toolchain.dslx_stdlib_path)),
        "dslx_path = {}".format(_toml_array(resolved_toolchain.dslx_path)),
        "enable_warnings = {}".format(_toml_array(resolved_toolchain.enable_warnings)),
        "disable_warnings = {}".format(_toml_array(resolved_toolchain.disable_warnings)),
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


def get_toolchain_artifact_inputs(toolchain):
    return getattr(toolchain, "artifact_inputs", [])


def _patch_dylib_impl(ctx):
    ctx.actions.run_shell(
        inputs = [ctx.file.src],
        outputs = [ctx.outputs.out],
        command = """
            cp {infile} {outfile}
            install_name_tool -id @rpath/{libname} {outfile}
        """.format(
            infile = ctx.file.src.path,
            outfile = ctx.outputs.out.path,
            libname = ctx.file.src.basename,
        ),
        progress_message = "Patching dylib install name",
    )
    return DefaultInfo(files = depset([ctx.outputs.out]))


patch_dylib = rule(
    implementation = _patch_dylib_impl,
    attrs = {
        "src": attr.label(mandatory = True, allow_single_file = True),
        "out": attr.output(),
    },
)


def _copy_flat_files_to_directory_impl(ctx):
    output = ctx.actions.declare_directory(ctx.label.name)
    input_paths = [src.path for src in ctx.files.srcs]
    ctx.actions.run_shell(
        inputs = ctx.files.srcs,
        outputs = [output],
        arguments = [output.path] + input_paths,
        command = """
            set -euo pipefail
            out="$1"
            shift
            mkdir -p "$out"
            for src in "$@"; do
                cp "$src" "$out/$(basename "$src")"
            done
        """,
        progress_message = "Copying files into {}".format(ctx.label),
    )
    return DefaultInfo(files = depset([output]))


copy_flat_files_to_directory = rule(
    implementation = _copy_flat_files_to_directory_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = True, mandatory = True),
    },
)


def _xls_shared_library_link_impl(ctx):
    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    shared_library = ctx.file.shared_library
    library_to_link = cc_common.create_library_to_link(
        actions = ctx.actions,
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        dynamic_library = shared_library,
    )
    linker_input = cc_common.create_linker_input(
        owner = ctx.label,
        libraries = depset([library_to_link]),
    )
    linking_context = cc_common.create_linking_context(
        linker_inputs = depset([linker_input]),
    )
    return [CcInfo(linking_context = linking_context)]


xls_shared_library_link = rule(
    implementation = _xls_shared_library_link_impl,
    attrs = {
        "shared_library": attr.label(mandatory = True, allow_single_file = True),
        "_cc_toolchain": attr.label(default = Label("@bazel_tools//tools/cpp:current_cc_toolchain")),
    },
    fragments = ["cpp"],
    toolchains = use_cpp_toolchain(),
)
