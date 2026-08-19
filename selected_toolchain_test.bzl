# SPDX-License-Identifier: Apache-2.0

"""Analysis coverage for the producer pins selected by DSLX libraries."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//:rules.bzl", "DslxSelectedToolchainInfo")
load("//:xls_toolchain.bzl", "xls_bundle")

_UPPERCASE_GIT_REVISION = "ABCDEF0123456789ABCDEF0123456789ABCDEF01"

def _selected_toolchain_test_impl(ctx):
    """Checks selected producer pins and preserves default-versus-opt-in outputs."""
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    selected = target[DslxSelectedToolchainInfo]

    if ctx.attr.expect_missing:
        asserts.equals(env, None, selected.xls_pin)
        asserts.equals(env, None, selected.xlsynth_crate_pin)
    else:
        asserts.equals(env, ctx.attr.expected_xls_kind, selected.xls_pin.kind)
        asserts.equals(env, ctx.attr.expected_xls_value, selected.xls_pin.value)
        asserts.equals(env, ctx.attr.expected_driver_kind, selected.xlsynth_crate_pin.kind)
        asserts.equals(env, ctx.attr.expected_driver_value, selected.xlsynth_crate_pin.value)

    default_outputs = target[DefaultInfo].files.to_list()
    asserts.equals(env, 1, len(default_outputs))
    asserts.true(env, default_outputs[0].basename.endswith(".typecheck"))

    metadata_outputs = target[OutputGroupInfo].selected_toolchain.to_list()
    asserts.equals(env, 1, len(metadata_outputs))
    asserts.true(env, metadata_outputs[0].basename.endswith(".selected_toolchain.json"))
    asserts.equals(env, metadata_outputs[0], selected.metadata)
    return analysistest.end(env)

_selected_toolchain_test = analysistest.make(
    _selected_toolchain_test_impl,
    attrs = {
        "expect_missing": attr.bool(),
        "expected_driver_kind": attr.string(),
        "expected_driver_value": attr.string(),
        "expected_xls_kind": attr.string(),
        "expected_xls_value": attr.string(),
    },
)

def _invalid_pin_test_impl(ctx):
    """Checks that malformed or ambiguous producer pins fail during analysis."""
    env = analysistest.begin(ctx)
    asserts.expect_failure(env, ctx.attr.expected_error)
    return analysistest.end(env)

_invalid_pin_test = analysistest.make(
    _invalid_pin_test_impl,
    attrs = {
        "expected_error": attr.string(mandatory = True),
    },
    expect_failure = True,
)

def _fake_bundle(name, **kwargs):
    """Creates an analysis-only bundle without materializing a second toolchain."""
    xls_bundle(
        name = name,
        driver = "//:LICENSE",
        runtime = "@rules_xlsynth_selftest_xls_runtime//:runtime",
        visibility = ["//sample:__pkg__"],
        **kwargs
    )

def selected_toolchain_test_suite(name):
    """Instantiates default, overridden, typed-pin, and failure analysis tests."""
    default_test = name + "_default"

    # Verifies: The registered default exposes independent canonical producer pins.
    # Catches: Incorrect default selection or changed normal library outputs.
    _selected_toolchain_test(
        name = default_test,
        target_under_test = "//sample:" + name + "_default_library",
        expected_xls_kind = "release_tag",
        expected_xls_value = "v0.40.0",
        expected_driver_kind = "release_tag",
        expected_driver_value = "v0.36.0",
    )

    override_bundle = name + "_override_bundle"
    _fake_bundle(
        name = override_bundle,
        xls_version = "0.37.0",
        xlsynth_driver_version = "0.32.0",
    )
    override_test = name + "_override"

    # Verifies: A library override exposes its own XLS and XLSynth versions.
    # Catches: Substituting the registered default for the target's selected bundle.
    _selected_toolchain_test(
        name = override_test,
        target_under_test = "//sample:" + name + "_override_library",
        expected_xls_kind = "release_tag",
        expected_xls_value = "v0.37.0",
        expected_driver_kind = "release_tag",
        expected_driver_value = "v0.32.0",
    )

    git_bundle = name + "_git_bundle"
    _fake_bundle(
        name = git_bundle,
        xls_git_revision = _UPPERCASE_GIT_REVISION,
        xlsynth_driver_git_revision = _UPPERCASE_GIT_REVISION,
    )
    git_test = name + "_git"

    # Verifies: Exact Git producer revisions are normalized to lowercase.
    # Catches: Ambiguous or noncanonical selected-toolchain producer identities.
    _selected_toolchain_test(
        name = git_test,
        target_under_test = "//sample:" + name + "_git_library",
        expected_xls_kind = "git_revision",
        expected_xls_value = _UPPERCASE_GIT_REVISION.lower(),
        expected_driver_kind = "git_revision",
        expected_driver_value = _UPPERCASE_GIT_REVISION.lower(),
    )

    unpinned_bundle = name + "_unpinned_bundle"
    _fake_bundle(name = unpinned_bundle)
    unpinned_test = name + "_unpinned"

    # Verifies: Versionless local bundles explicitly expose unavailable pins.
    # Catches: Breaking existing locally configured toolchains during analysis.
    _selected_toolchain_test(
        name = unpinned_test,
        target_under_test = "//sample:" + name + "_unpinned_library",
        expect_missing = True,
    )

    invalid_release_bundle = name + "_invalid_release_bundle"
    _fake_bundle(
        name = invalid_release_bundle,
        tags = ["manual"],
        xls_version = "invalid/release",
    )
    invalid_release_test = name + "_invalid_release"

    # Negative test: Invalid release tags exercise producer-pin error handling.
    _invalid_pin_test(
        name = invalid_release_test,
        target_under_test = ":" + invalid_release_bundle,
        expected_error = "Expected release tag",
    )

    invalid_revision_bundle = name + "_invalid_revision_bundle"
    _fake_bundle(
        name = invalid_revision_bundle,
        tags = ["manual"],
        xls_git_revision = "not-an-exact-git-revision",
    )
    invalid_revision_test = name + "_invalid_revision"

    # Negative test: Inexact Git revisions exercise producer-pin error handling.
    _invalid_pin_test(
        name = invalid_revision_test,
        target_under_test = ":" + invalid_revision_bundle,
        expected_error = "Expected exact 40-character Git revision",
    )

    ambiguous_bundle = name + "_ambiguous_bundle"
    _fake_bundle(
        name = ambiguous_bundle,
        tags = ["manual"],
        xls_version = "0.40.0",
        xls_git_revision = _UPPERCASE_GIT_REVISION,
    )
    ambiguous_test = name + "_ambiguous"

    # Negative test: Conflicting pin representations exercise error handling.
    _invalid_pin_test(
        name = ambiguous_test,
        target_under_test = ":" + ambiguous_bundle,
        expected_error = "either a release tag or a Git revision, not both",
    )

    native.test_suite(
        name = name,
        tests = [
            ":" + default_test,
            ":" + override_test,
            ":" + git_test,
            ":" + unpinned_test,
            ":" + invalid_release_test,
            ":" + invalid_revision_test,
            ":" + ambiguous_test,
        ],
    )
