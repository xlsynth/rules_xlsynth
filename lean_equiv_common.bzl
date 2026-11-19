# SPDX-License-Identifier: Apache-2.0
"""Test executable and runfiles shared by Lean function and netlist proofs."""

load(":xls_toolchain.bzl", "XlsArtifactBundleInfo", "get_driver_artifact_inputs")

LEAN_PROOF_ATTRS = {
    "proof": attr.label(allow_single_file = [".lean"], mandatory = True, doc = "Lean module containing the selected equivalence theorem."),
    "proof_theorem": attr.string(mandatory = True, doc = "Fully qualified name of the theorem proving Target.Equivalent."),
    "proof_srcs": attr.label_list(allow_files = [".lean"], doc = "Additional Lean modules available for the proof to import."),
    "allow_native_checks": attr.bool(default = True, doc = "Allow replaying native Boolean checks. Set to False to require only the three standard Lean axioms."),
    "xls_bundle": attr.label(providers = [XlsArtifactBundleInfo], doc = "Optional XLS bundle override for target preparation, the proof driver, and the Lean distribution."),
    "_input_checker": attr.label(default = Label("//:verify_lean_input.py"), allow_single_file = True),
    "_test_runner": attr.label(default = Label("//:lean_equiv_runner.py"), allow_single_file = True),
}

def lean_proof_input(ctx, side, source, expected_hash, kind):
    """Returns the exact proof input, with a hash-check action when a digest is required."""
    if kind == "IR" and not expected_hash:
        return struct(file = source, metadata = None, sha256 = None)

    digest = expected_hash.lower()
    attr_name = side + ("_ir_sha256" if kind == "IR" else "_sha256")
    if len(digest) != 64 or any([c not in "0123456789abcdef" for c in digest.elems()]):
        fail("{} must contain exactly 64 hexadecimal characters".format(attr_name))
    extension = "ir" if kind == "IR" else "gv"
    verified = ctx.actions.declare_file(ctx.label.name + "." + side + ".verified." + extension)
    metadata = ctx.actions.declare_file(ctx.label.name + "." + side + ".hash.json")
    ctx.actions.run_shell(
        inputs = [source, ctx.file._input_checker],
        outputs = [verified, metadata],
        arguments = [ctx.file._input_checker.path, source.path, digest, verified.path, metadata.path, side, kind],
        command = 'python3 "$1" --input "$2" --expected-hash "$3" --output "$4" --metadata "$5" --side "$6" --kind "$7"',
        env = {"PATH": "/usr/bin:/bin"},
        progress_message = "Verifying {} {} content for {}".format(side, kind, ctx.label),
        mnemonic = "XlsynthIrHash" if kind == "IR" else "XlsynthNetlistHash",
    )
    return struct(file = verified, metadata = metadata, sha256 = digest)

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

def lean_proof_test(ctx, toolchain, toolchain_file, target, check_settings, proof_inputs):
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
        "allow_native_checks": ctx.attr.allow_native_checks,
        "driver": lean_runfile_path(ctx, toolchain.driver),
        "lean_root": lean_runfile_path(ctx, toolchain.lean.root),
        "lean_version": toolchain.lean.version,
        "proof": proof,
        "proof_theorem": ctx.attr.proof_theorem,
        "proof_srcs": proof_srcs,
        "runtime_library": lean_runfile_path(ctx, toolchain.libxls) if toolchain.libxls else None,
        "target": lean_runfile_path(ctx, target),
        "toolchain": lean_runfile_path(ctx, toolchain_file),
    }
    settings.update(check_settings)
    hash_files = []
    for side, proof_input in proof_inputs.items():
        if proof_input.metadata:
            settings[side + "_hash"] = proof_input.sha256
            settings[side + "_hash_metadata"] = lean_runfile_path(ctx, proof_input.metadata)
            hash_files.append(proof_input.metadata)
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
            ] + ctx.files.proof_srcs + hash_files + get_driver_artifact_inputs(toolchain)),
        ),
        OutputGroupInfo(lean_target = depset([target])),
    ]
