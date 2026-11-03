# SPDX-License-Identifier: Apache-2.0

"""Checks explicit DSLX roots at their action and interpreter boundaries."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load(
    "//:rules.bzl",
    "DslxInfo",
    "dslx_library",
    "dslx_prove_quickcheck_test",
    "dslx_stitch_pipeline",
    "dslx_test",
    "dslx_to_ir",
    "dslx_to_pipeline",
    "dslx_to_pipeline_eco",
    "dslx_to_sv_types",
)
load("//:xls_toolchain.bzl", "xls_bundle")

_LEAF = "//sample_expecting_dslx_path/subdir:another.x"
_SOURCES = ["root.x", "support.x", _LEAF]

def _source_paths(files):
    # The runtime bundle also contains external stdlib sources.
    return sorted([f.short_path for f in files if f.extension == "x" and not f.short_path.startswith("../")])

def _action_root_test_impl(ctx):
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    actions = [a for a in analysistest.target_actions(env) if ctx.attr.command in (a.argv or [])]
    asserts.equals(env, 1, len(actions))
    if len(actions) == 1:
        argv = actions[0].argv
        root = ctx.file.root.path
        pairs = [argv[i:i + 2] for i in range(len(argv) - 1)]
        asserts.true(
            env,
            [ctx.attr.root_flag, root] in pairs or ctx.attr.root_flag + "=" + root in argv,
            "Expected the selected root after " + ctx.attr.root_flag + ": " + str(argv),
        )
        asserts.equals(env, _source_paths(ctx.files.sources), _source_paths(actions[0].inputs.to_list()))
    if DslxInfo in target:
        asserts.equals(env, ctx.file.root, target[DslxInfo].root)
        asserts.equals(env, _source_paths(ctx.files.sources), _source_paths(target[DslxInfo].transitive_srcs.to_list()))
    if ctx.attr.command == "dslx2ir":
        optimizers = [a for a in analysistest.target_actions(env) if "ir2opt" in (a.argv or [])]
        asserts.equals(env, 1, len(optimizers))
        if len(optimizers) == 1:
            argv = optimizers[0].argv
            asserts.equals(env, "__root__main", argv[argv.index("--top") + 1])
    return analysistest.end(env)

_action_root_test = analysistest.make(
    _action_root_test_impl,
    attrs = {
        "command": attr.string(mandatory = True),
        "root": attr.label(allow_single_file = [".x"], mandatory = True),
        "root_flag": attr.string(default = "--dslx_input_file"),
        "sources": attr.label_list(allow_files = [".x"]),
    },
)

def _script_root_test_impl(ctx):
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    executable = target[DefaultInfo].files_to_run.executable
    scripts = [a for a in analysistest.target_actions(env) if executable in a.outputs.to_list()]
    asserts.equals(env, 1, len(scripts))
    if len(scripts) == 1:
        # These fixture paths contain no shell metacharacters or spaces.
        words = scripts[0].content.replace('"', "").replace("'", "").replace("\n", " ").split(" ")
        asserts.true(env, ctx.attr.root_flag in words)
        if ctx.attr.root_flag in words:
            asserts.equals(env, ctx.file.root.short_path, words[words.index(ctx.attr.root_flag) + 1])
    runfiles = target[DefaultInfo].default_runfiles.files.to_list()
    asserts.equals(env, _source_paths(ctx.files.sources), _source_paths(runfiles))
    asserts.equals(env, [], [f.short_path for f in runfiles if f.basename.endswith(".typecheck")])
    return analysistest.end(env)

_script_root_test = analysistest.make(
    _script_root_test_impl,
    attrs = {
        "root": attr.label(allow_single_file = [".x"], mandatory = True),
        "root_flag": attr.string(default = "dslx_interpreter_main"),
        "sources": attr.label_list(allow_files = [".x"]),
    },
)

def _invalid_root_test_impl(ctx):
    env = analysistest.begin(ctx)
    asserts.expect_failure(env, ctx.attr.error)
    return analysistest.end(env)

_invalid_root_test = analysistest.make(
    _invalid_root_test_impl,
    expect_failure = True,
    attrs = {"error": attr.string(mandatory = True)},
)

def root_selection_test_suite(name):
    """Creates bounded action checks and real interpreter fixtures."""
    xls_bundle(
        name = "analysis_bundle",
        driver = ":BUILD.bazel",
        runtime = "@rules_xlsynth_selftest_xls_runtime//:runtime",
    )
    common = {"tags": ["manual"], "xls_bundle": ":analysis_bundle"}
    dslx_library(name = "leaf", srcs = [_LEAF], **common)
    dslx_library(name = "support", srcs = ["support.x"], deps = [":leaf"], **common)
    dslx_library(name = "extra", srcs = ["failing_root.x"], deps = [":support"], **common)
    tests = []
    for order, srcs in [
        ("first", ["root.x", "support.x"]),
        ("last", ["support.x", "root.x"]),
    ]:
        library = "root_" + order
        dslx_library(name = library, srcs = srcs, root = "root.x", deps = [":leaf"], **common)
        _action_root_test(
            name = library + "_analysis_test",
            target_under_test = ":" + library,
            command = "typecheck_main",
            root_flag = "typecheck_main",
            root = "root.x",
            sources = _SOURCES,
        )
        tests.append(":" + library + "_analysis_test")
        dslx_test(name = library + "_test", lib = ":" + library, deps = [":extra"], **common)
        _script_root_test(
            name = library + "_script_test",
            target_under_test = ":" + library + "_test",
            root = "root.x",
            sources = _SOURCES + ["failing_root.x"],
        )
        tests.append(":" + library + "_script_test")

        # Both source orders must expose a failing root, never select support.x.
        for prefix, root in [("failing", "failing_root.x"), ("invalid", "invalid_root.x")]:
            sources = [root, "support.x"] if order == "first" else ["support.x", root]
            dslx_library(
                name = prefix + "_" + order,
                srcs = sources,
                root = root,
                deps = [":leaf"],
                **common
            )
        dslx_test(name = "failing_" + order + "_test", lib = ":failing_" + order, **common)

    # The two convenient interpreter call forms must select the same root.
    dslx_test(name = "src_test", src = "root.x", deps = [":support"], **common)
    dslx_test(name = "single_dep_test", deps = [":root_last"], **common)
    for target in ["src_test", "single_dep_test"]:
        _script_root_test(
            name = target + "_analysis_test",
            target_under_test = ":" + target,
            root = "root.x",
            sources = _SOURCES,
        )
        tests.append(":" + target + "_analysis_test")

    _action_root_test(
        name = "singleton_analysis_test",
        target_under_test = ":support",
        command = "typecheck_main",
        root_flag = "typecheck_main",
        root = "support.x",
        sources = ["support.x", _LEAF],
    )
    tests.append(":singleton_analysis_test")

    dslx_to_ir(name = "root_ir", lib = ":root_first", top = "main", **common)
    dslx_stitch_pipeline(name = "root_stitch", lib = ":root_first", top = "root", **common)
    dslx_prove_quickcheck_test(name = "root_proof_test", lib = ":root_first", **common)
    _script_root_test(
        name = "proof_analysis_test",
        target_under_test = ":root_proof_test",
        root = "root.x",
        root_flag = "--dslx_input_file",
        sources = _SOURCES,
    )
    tests.append(":proof_analysis_test")

    for suffix, converter, command, options in [
        ("pipeline", dslx_to_pipeline, "dslx2pipeline", {"top": "main", "delay_model": "unit", "pipeline_stages": 1}),
        ("eco", dslx_to_pipeline_eco, "dslx2pipeline-eco", {"top": "main", "delay_model": "unit", "pipeline_stages": 1, "baseline_unopt_ir": ":root_ir.ir"}),
        ("sv_types", dslx_to_sv_types, "dslx2sv-types", {"sv_enum_case_naming_policy": "unqualified"}),
    ]:
        converter(name = "root_" + suffix, lib = ":root_first", deps = [":extra"], **dict(common, **options))
        _action_root_test(
            name = suffix + "_analysis_test",
            target_under_test = ":root_" + suffix,
            command = command,
            root = "root.x",
            sources = _SOURCES + ["failing_root.x"],
        )
        tests.append(":" + suffix + "_analysis_test")
        converter(name = "ambiguous_" + suffix, deps = [":root_first", ":extra"], **dict(common, **options))
        _invalid_root_test(
            name = suffix + "_ambiguous_test",
            target_under_test = ":ambiguous_" + suffix,
            error = "exactly one dependency",
        )
        tests.append(":" + suffix + "_ambiguous_test")

    for suffix, command in [("ir", "dslx2ir"), ("stitch", "dslx-stitch-pipeline")]:
        _action_root_test(
            name = suffix + "_analysis_test",
            target_under_test = ":root_" + suffix,
            command = command,
            root = "root.x",
            sources = _SOURCES,
        )
        tests.append(":" + suffix + "_analysis_test")

    for target, options, error in [
        ("missing_root", {"srcs": ["root.x", "support.x"]}, "must specify root when srcs does not contain exactly one file"),
        ("missing_source", {"srcs": [], "deps": [":support"]}, "must specify root when srcs does not contain exactly one file"),
        ("outside_root", {"srcs": ["root.x"], "root": "support.x", "deps": [":support"]}, "root must be one of the direct srcs"),
    ]:
        dslx_library(name = target, **dict(common, **options))
        _invalid_root_test(name = target + "_test", target_under_test = ":" + target, error = error)
        tests.append(":" + target + "_test")

    native.test_suite(name = name, tests = tests)
