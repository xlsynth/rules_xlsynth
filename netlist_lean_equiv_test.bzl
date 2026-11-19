# SPDX-License-Identifier: Apache-2.0
"""A Bazel test for supplied Lean proofs of mapped-netlist equivalence."""

load(":env_helpers.bzl", "python_runner_source")
load(":lean_equiv_common.bzl", "LEAN_PROOF_ATTRS", "lean_proof_input", "lean_proof_test")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "require_lean_toolchain")

def _driver_arguments(toolchain, toolchain_file):
    arguments = [
        "driver",
        "--driver_path",
        toolchain.driver_path,
        "--toolchain",
        toolchain_file.path,
    ]
    if toolchain.runtime_library_path:
        arguments.extend(["--runtime_library_path", toolchain.runtime_library_path])
    return arguments

def _logic_cone(sources, sinks, prefix):
    if sources and not sinks:
        fail("{}logic_cone_sources requires {}logic_cone_sinks".format(prefix, prefix))
    return struct(sources = sources, sinks = sinks)

def _resolve_logic_cones(ctx):
    """Resolves shared or per-side selectors into one selection per netlist."""
    shared = bool(ctx.attr.logic_cone_sources or ctx.attr.logic_cone_sinks)
    per_side = bool(
        ctx.attr.lhs_logic_cone_sources or
        ctx.attr.lhs_logic_cone_sinks or
        ctx.attr.rhs_logic_cone_sources or
        ctx.attr.rhs_logic_cone_sinks,
    )
    if shared and per_side:
        fail("logic_cone_sources/logic_cone_sinks cannot be combined with lhs_logic_cone_* or rhs_logic_cone_* attributes")
    if shared:
        cone = _logic_cone(ctx.attr.logic_cone_sources, ctx.attr.logic_cone_sinks, "")
        return struct(lhs = cone, rhs = cone)
    return struct(
        lhs = _logic_cone(ctx.attr.lhs_logic_cone_sources, ctx.attr.lhs_logic_cone_sinks, "lhs_"),
        rhs = _logic_cone(ctx.attr.rhs_logic_cone_sources, ctx.attr.rhs_logic_cone_sinks, "rhs_"),
    )

def _convert_netlist(ctx, side, verified, cone, top, toolchain, toolchain_file, runner):
    graph = ctx.actions.declare_file(ctx.label.name + "." + side + ".g8r")
    arguments = _driver_arguments(toolchain, toolchain_file) + [
        "--stdout_path",
        graph.path,
        "gv2g8r",
        "--netlist",
        verified.path,
        "--liberty_proto",
        ctx.file.liberty_proto.path,
        "--collapse_sequential_cells",
        "true" if ctx.attr.collapse_sequential_cells else "false",
    ]
    inputs = [verified, ctx.file.liberty_proto, toolchain_file]
    if top:
        arguments.extend(["--module_name", top])
    for source in cone.sources:
        arguments.extend(["--cone_sources", source])
    for sink in cone.sinks:
        arguments.extend(["--cone_sinks", sink])
    if ctx.attr.collapse_load_enable_feedback:
        arguments.append("--collapse_load_enable_feedback")
    ctx.actions.run(
        executable = runner,
        inputs = inputs + get_driver_artifact_inputs(toolchain),
        outputs = [graph],
        arguments = arguments,
        use_default_shell_env = False,
        progress_message = "Converting {} netlist for {}".format(side, ctx.label),
        mnemonic = "XlsynthNetlistToG8r",
    )
    return graph

def _netlist_lean_equiv_test_impl(ctx):
    cones = _resolve_logic_cones(ctx)
    if ctx.attr.collapse_load_enable_feedback and not ctx.attr.collapse_sequential_cells:
        fail("collapse_load_enable_feedback requires collapse_sequential_cells = True")
    toolchain = require_lean_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "netlist_lean_equiv", toolchain = toolchain)
    driver_runner = ctx.actions.declare_file(ctx.label.name + "_driver.py")
    ctx.actions.write(output = driver_runner, content = python_runner_source(), is_executable = True)

    lhs = lean_proof_input(ctx, "lhs", ctx.file.lhs, ctx.attr.lhs_sha256, "netlist")
    rhs = lean_proof_input(ctx, "rhs", ctx.file.rhs, ctx.attr.rhs_sha256, "netlist")
    lhs_graph = _convert_netlist(ctx, "lhs", lhs.file, cones.lhs, ctx.attr.lhs_top, toolchain, toolchain_file, driver_runner)
    rhs_graph = _convert_netlist(ctx, "rhs", rhs.file, cones.rhs, ctx.attr.rhs_top, toolchain, toolchain_file, driver_runner)
    target = ctx.actions.declare_directory(ctx.label.name + ".lean_target")
    prepare_args = _driver_arguments(toolchain, toolchain_file) + [
        "g8r-lean-prepare",
        "--lhs",
        lhs_graph.path,
        "--rhs",
        rhs_graph.path,
        "--output-dir",
        target.path,
    ]
    if not ctx.attr.allow_native_checks:
        prepare_args.append("--reject-native-checks")
    ctx.actions.run(
        executable = driver_runner,
        inputs = [lhs_graph, rhs_graph, toolchain_file] + get_driver_artifact_inputs(toolchain),
        outputs = [target],
        arguments = prepare_args,
        use_default_shell_env = False,
        progress_message = "Generating Lean equivalence target for {}".format(ctx.label),
        mnemonic = "XlsynthLeanPrepare",
    )

    return lean_proof_test(ctx, toolchain, toolchain_file, target, {
        "check_command": "g8r-lean-check",
        "extraction": {
            "collapse_load_enable_feedback": ctx.attr.collapse_load_enable_feedback,
            "collapse_sequential": ctx.attr.collapse_sequential_cells,
            "lhs_logic_cone_sources": cones.lhs.sources,
            "lhs_logic_cone_sinks": cones.lhs.sinks,
            "lhs_top": ctx.attr.lhs_top,
            "rhs_logic_cone_sources": cones.rhs.sources,
            "rhs_logic_cone_sinks": cones.rhs.sinks,
            "rhs_top": ctx.attr.rhs_top,
        },
    }, {"lhs": lhs, "rhs": rhs})

netlist_lean_equiv_test = rule(
    doc = "Checks and audits a named Lean theorem proving equivalence of two mapped netlists.",
    implementation = _netlist_lean_equiv_test_impl,
    attrs = dict(
        LEAN_PROOF_ATTRS,
        lhs = attr.label(allow_single_file = True, mandatory = True),
        lhs_sha256 = attr.string(mandatory = True),
        rhs = attr.label(allow_single_file = True, mandatory = True),
        rhs_sha256 = attr.string(mandatory = True),
        liberty_proto = attr.label(allow_single_file = True, mandatory = True),
        lhs_top = attr.string(),
        rhs_top = attr.string(),
        logic_cone_sources = attr.string_list(doc = "Compact source selectors applied to both netlists."),
        logic_cone_sinks = attr.string_list(doc = "Compact sink selectors applied to both netlists."),
        lhs_logic_cone_sources = attr.string_list(doc = "Compact source selectors for the LHS netlist."),
        lhs_logic_cone_sinks = attr.string_list(doc = "Compact sink selectors for the LHS netlist."),
        rhs_logic_cone_sources = attr.string_list(doc = "Compact source selectors for the RHS netlist."),
        rhs_logic_cone_sinks = attr.string_list(doc = "Compact sink selectors for the RHS netlist."),
        collapse_sequential_cells = attr.bool(default = False),
        collapse_load_enable_feedback = attr.bool(default = False),
    ),
    test = True,
    executable = True,
    toolchains = ["//:toolchain_type"],
)
