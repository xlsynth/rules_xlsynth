# SPDX-License-Identifier: Apache-2.0
"""Test executable and runfiles shared by Lean function and netlist proofs."""

load(":xls_toolchain.bzl", "get_driver_artifact_inputs")

def lean_runfile_path(ctx, artifact):
    """Returns the logical path of a proof input in the test runfiles."""
    if artifact.short_path.startswith("../"):
        return artifact.short_path[3:]
    return ctx.workspace_name + "/" + artifact.short_path

def _proof_file(ctx, artifact, root):
    if artifact.is_directory or artifact.extension != "lean":
        fail("proof inputs must be .lean files: {}".format(artifact.path))
    runfile = lean_runfile_path(ctx, artifact)
    prefix = root + "/"
    if not runfile.startswith(prefix):
        fail("{} must be under the directory containing the proof file".format(artifact.path))
    return {"relative": runfile[len(prefix):], "runfile": runfile}

def lean_proof_test(ctx, toolchain, toolchain_file, target, check_settings, extra_runfiles = []):
    """Packages the prepared target, proof sources, and selected tools for the runner."""
    proof_runfile = lean_runfile_path(ctx, ctx.file.proof)
    proof_root = proof_runfile.rsplit("/", 1)[0]
    proof = _proof_file(ctx, ctx.file.proof, proof_root)
    proof_srcs = [_proof_file(ctx, file, proof_root) for file in ctx.files.proof_srcs]
    seen = {}
    for item in [proof] + proof_srcs:
        if item["relative"] in seen:
            fail("duplicate proof input path: {}".format(item["relative"]))
        seen[item["relative"]] = True

    config = ctx.actions.declare_file(ctx.label.name + ".test.json")
    settings = {
        "driver": lean_runfile_path(ctx, toolchain.driver),
        "lean_root": lean_runfile_path(ctx, toolchain.lean.root),
        "lean_version": toolchain.lean.version,
        "proof": proof,
        "proof_srcs": proof_srcs,
        "runtime_library": lean_runfile_path(ctx, toolchain.libxls) if toolchain.libxls else None,
        "target": lean_runfile_path(ctx, target),
        "toolchain": lean_runfile_path(ctx, toolchain_file),
    }
    settings.update(check_settings)
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
            ] + ctx.files.proof_srcs + extra_runfiles + get_driver_artifact_inputs(toolchain)),
        ),
        OutputGroupInfo(lean_target = depset([target])),
    ]
