# SPDX-License-Identifier: Apache-2.0
"""Shared actions and runfiles for the two Lean equivalence checkers."""

load(":xls_toolchain.bzl", "get_driver_artifact_inputs")

def lean_runfile_path(ctx, artifact):
    """Returns the logical path of a proof input in the test runfiles."""
    if artifact.short_path.startswith("../"):
        return artifact.short_path[3:]
    return ctx.workspace_name + "/" + artifact.short_path

def lean_driver_arguments(toolchain, toolchain_file):
    """Selects the driver and its runtime for a Lean preparation action."""
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

def _proof_file(ctx, artifact, root, kind):
    if artifact.is_directory:
        fail("{} must contain files, not directories: {}".format(kind, artifact.path))
    runfile = lean_runfile_path(ctx, artifact)
    prefix = root + "/"
    if not runfile.startswith(prefix):
        fail("{} file {} must be under the directory containing the proof file".format(kind, artifact.path))
    relative = runfile[len(prefix):]
    if kind == "proof_srcs" and not relative.endswith(".lean"):
        fail("proof_srcs file must have a .lean extension: {}".format(artifact.path))
    return {"relative": relative, "runfile": runfile}

def lean_equiv_test_result(ctx, target, toolchain, toolchain_file, checker, metadata = {}, metadata_files = []):
    """Stages the supplied proof and runs the checker for a prepared Lean target."""
    proof_runfile = lean_runfile_path(ctx, ctx.file.proof)
    proof_root = proof_runfile.rsplit("/", 1)[0]
    proof = _proof_file(ctx, ctx.file.proof, proof_root, "proof")
    proof_srcs = [_proof_file(ctx, file, proof_root, "proof_srcs") for file in ctx.files.proof_srcs]
    seen = {}
    for item in [proof] + proof_srcs:
        if item["relative"] in seen:
            fail("duplicate proof input path: {}".format(item["relative"]))
        seen[item["relative"]] = True

    config = ctx.actions.declare_file(ctx.label.name + ".test.json")
    settings = dict(metadata)
    settings.update({
        "checker": checker,
        "driver": lean_runfile_path(ctx, toolchain.driver),
        "lean_root": lean_runfile_path(ctx, toolchain.lean.root),
        "lean_version": toolchain.lean.version,
        "proof": proof,
        "proof_srcs": proof_srcs,
        "runtime_library": lean_runfile_path(ctx, toolchain.libxls) if toolchain.libxls else None,
        "target": lean_runfile_path(ctx, target),
        "toolchain": lean_runfile_path(ctx, toolchain_file),
    })
    ctx.actions.write(output = config, content = json.encode(settings) + "\n")
    runner = ctx.actions.declare_file(ctx.label.name + "_test.py")
    ctx.actions.expand_template(
        template = ctx.file._test_runner,
        output = runner,
        substitutions = {"@CONFIG_RUNFILE@": json.encode(lean_runfile_path(ctx, config))[1:-1]},
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
                ctx.file.proof,
            ] + ctx.files.proof_srcs + metadata_files + get_driver_artifact_inputs(toolchain)),
        ),
        OutputGroupInfo(lean_target = depset([target])),
    ]
