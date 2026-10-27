# SPDX-License-Identifier: Apache-2.0
"""A Bazel test for supplied Lean proofs of mapped-netlist equivalence."""

load(":env_helpers.bzl", "python_runner_source")
load(":xls_toolchain.bzl", "declare_xls_toolchain_toml", "get_driver_artifact_inputs", "require_lean_toolchain")

def _runfile_path(ctx, artifact):
    if artifact.short_path.startswith("../"):
        return artifact.short_path[3:]
    return ctx.workspace_name + "/" + artifact.short_path

def _validate_hash(value, side):
    normalized = value.lower()
    if len(normalized) != 64:
        fail("{}_sha256 must contain exactly 64 hexadecimal characters".format(side))
    for index in range(len(normalized)):
        if normalized[index] not in "0123456789abcdef":
            fail("{}_sha256 must contain exactly 64 hexadecimal characters".format(side))
    return normalized

def _verify_input(ctx, side, source, expected_hash):
    verified = ctx.actions.declare_file(ctx.label.name + "." + side + ".verified.gv")
    metadata = ctx.actions.declare_file(ctx.label.name + "." + side + ".hash.json")
    ctx.actions.run_shell(
        inputs = [source, ctx.file._input_checker],
        outputs = [verified, metadata],
        arguments = [
            ctx.file._input_checker.path,
            source.path,
            expected_hash,
            verified.path,
            metadata.path,
            side,
        ],
        command = 'python3 "$1" --input "$2" --expected-hash "$3" --output "$4" --metadata "$5" --side "$6"',
        env = {"PATH": "/usr/bin:/bin"},
        progress_message = "Verifying {} netlist content for {}".format(side, ctx.label),
        mnemonic = "XlsynthNetlistHash",
    )
    return struct(netlist = verified, metadata = metadata)

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

def _convert_netlist(ctx, side, verified, boundary, top, toolchain, toolchain_file, runner):
    graph = ctx.actions.declare_file(ctx.label.name + "." + side + ".g8r")
    arguments = _driver_arguments(toolchain, toolchain_file) + [
        "--stdout_path",
        graph.path,
        "gv2g8r",
        "--netlist",
        verified.path,
        "--liberty_proto",
        ctx.file.liberty_proto.path,
        "--collapse_sequential",
        "true" if ctx.attr.collapse_sequential else "false",
    ]
    inputs = [verified, ctx.file.liberty_proto, toolchain_file]
    if top:
        arguments.extend(["--module_name", top])
    if boundary:
        arguments.extend(["--cone_boundary_file", boundary.path])
        inputs.append(boundary)
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

def _proof_file(ctx, artifact, root, kind):
    if artifact.is_directory:
        fail("{} must contain files, not directories: {}".format(kind, artifact.path))
    runfile = _runfile_path(ctx, artifact)
    prefix = root + "/"
    if not runfile.startswith(prefix):
        fail("{} file {} must be under the proof body's directory".format(kind, artifact.path))
    relative = runfile[len(prefix):]
    if kind == "proof_srcs" and not relative.endswith(".lean"):
        fail("proof_srcs file must have a .lean extension: {}".format(artifact.path))
    return {"relative": relative, "runfile": runfile}

def _netlist_lean_equiv_test_impl(ctx):
    lhs_hash = _validate_hash(ctx.attr.lhs_sha256, "lhs")
    rhs_hash = _validate_hash(ctx.attr.rhs_sha256, "rhs")
    if ctx.attr.collapse_load_enable_feedback and not ctx.attr.collapse_sequential:
        fail("collapse_load_enable_feedback requires collapse_sequential = True")
    toolchain = require_lean_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "netlist_lean_equiv", toolchain = toolchain)
    driver_runner = ctx.actions.declare_file(ctx.label.name + "_driver.py")
    ctx.actions.write(output = driver_runner, content = python_runner_source(), is_executable = True)

    lhs = _verify_input(ctx, "lhs", ctx.file.lhs, lhs_hash)
    rhs = _verify_input(ctx, "rhs", ctx.file.rhs, rhs_hash)
    lhs_graph = _convert_netlist(ctx, "lhs", lhs.netlist, ctx.file.lhs_cone_boundary_file, ctx.attr.lhs_top, toolchain, toolchain_file, driver_runner)
    rhs_graph = _convert_netlist(ctx, "rhs", rhs.netlist, ctx.file.rhs_cone_boundary_file, ctx.attr.rhs_top, toolchain, toolchain_file, driver_runner)
    target = ctx.actions.declare_directory(ctx.label.name + ".lean_target")
    ctx.actions.run(
        executable = driver_runner,
        inputs = [lhs_graph, rhs_graph, toolchain_file] + get_driver_artifact_inputs(toolchain),
        outputs = [target],
        arguments = _driver_arguments(toolchain, toolchain_file) + [
            "g8r-lean-prepare",
            "--lhs",
            lhs_graph.path,
            "--rhs",
            rhs_graph.path,
            "--output-dir",
            target.path,
        ],
        use_default_shell_env = False,
        progress_message = "Generating Lean equivalence target for {}".format(ctx.label),
        mnemonic = "XlsynthLeanPrepare",
    )

    proof_runfile = _runfile_path(ctx, ctx.file.proof)
    proof_root = proof_runfile.rsplit("/", 1)[0]
    proof = _proof_file(ctx, ctx.file.proof, proof_root, "proof")
    proof_srcs = [_proof_file(ctx, file, proof_root, "proof_srcs") for file in ctx.files.proof_srcs]
    seen = {}
    for item in [proof] + proof_srcs:
        if item["relative"] in seen:
            fail("duplicate proof input path: {}".format(item["relative"]))
        seen[item["relative"]] = True

    config = ctx.actions.declare_file(ctx.label.name + ".test.json")
    ctx.actions.write(
        output = config,
        content = json.encode({
            "driver": _runfile_path(ctx, toolchain.driver),
            "extraction": {
                "collapse_load_enable_feedback": ctx.attr.collapse_load_enable_feedback,
                "collapse_sequential": ctx.attr.collapse_sequential,
                "lhs_cone_boundary_file": str(ctx.attr.lhs_cone_boundary_file.label) if ctx.attr.lhs_cone_boundary_file else None,
                "lhs_top": ctx.attr.lhs_top,
                "rhs_cone_boundary_file": str(ctx.attr.rhs_cone_boundary_file.label) if ctx.attr.rhs_cone_boundary_file else None,
                "rhs_top": ctx.attr.rhs_top,
            },
            "lean_root": _runfile_path(ctx, toolchain.lean.root),
            "lean_version": toolchain.lean.version,
            "lhs_hash": lhs_hash,
            "lhs_hash_metadata": _runfile_path(ctx, lhs.metadata),
            "proof": proof,
            "proof_srcs": proof_srcs,
            "rhs_hash": rhs_hash,
            "rhs_hash_metadata": _runfile_path(ctx, rhs.metadata),
            "runtime_library": _runfile_path(ctx, toolchain.libxls) if toolchain.libxls else None,
            "target": _runfile_path(ctx, target),
            "toolchain": _runfile_path(ctx, toolchain_file),
        }) + "\n",
    )
    runner = ctx.actions.declare_file(ctx.label.name + "_test.py")
    ctx.actions.expand_template(
        template = ctx.file._test_runner,
        output = runner,
        substitutions = {"@CONFIG_RUNFILE@": json.encode(_runfile_path(ctx, config))[1:-1]},
        is_executable = True,
    )
    return [
        DefaultInfo(
            executable = runner,
            files = depset([runner]),
            runfiles = ctx.runfiles(files = [
                config,
                target,
                toolchain_file,
                toolchain.lean.root,
                lhs.metadata,
                rhs.metadata,
                ctx.file.proof,
            ] + ctx.files.proof_srcs + get_driver_artifact_inputs(toolchain)),
        ),
        OutputGroupInfo(lean_target = depset([target])),
    ]

netlist_lean_equiv_test = rule(
    doc = "Mechanically converts two mapped netlists and checks a supplied Lean proof body. Lean proof auditing is not performed.",
    implementation = _netlist_lean_equiv_test_impl,
    attrs = {
        "lhs": attr.label(allow_single_file = True, mandatory = True),
        "lhs_sha256": attr.string(mandatory = True),
        "rhs": attr.label(allow_single_file = True, mandatory = True),
        "rhs_sha256": attr.string(mandatory = True),
        "liberty_proto": attr.label(allow_single_file = True, mandatory = True),
        "lhs_top": attr.string(),
        "rhs_top": attr.string(),
        "lhs_cone_boundary_file": attr.label(allow_single_file = True),
        "rhs_cone_boundary_file": attr.label(allow_single_file = True),
        "collapse_sequential": attr.bool(default = False),
        "collapse_load_enable_feedback": attr.bool(default = False),
        "proof": attr.label(allow_single_file = [".lean"], mandatory = True),
        "proof_srcs": attr.label_list(allow_files = [".lean"]),
        "_input_checker": attr.label(default = Label("//:verify_netlist_input.py"), allow_single_file = True),
        "_test_runner": attr.label(default = Label("//:netlist_lean_equiv_runner.py"), allow_single_file = True),
    },
    test = True,
    executable = True,
    toolchains = ["//:toolchain_type"],
)
