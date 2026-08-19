# SPDX-License-Identifier: Apache-2.0

"""Analysis coverage for the producer pins selected by DSLX libraries."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//:rules.bzl", "DslxSelectedToolchainInfo")
load("//:xls_toolchain.bzl", "XlsArtifactBundleInfo", "xls_bundle")

_UPPERCASE_GIT_REVISION = "ABCDEF0123456789ABCDEF0123456789ABCDEF01"
_OTHER_UPPERCASE_GIT_REVISION = "1234567890ABCDEF1234567890ABCDEF12345678"

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

def _legacy_bundle_impl(ctx):
    """Constructs external public bundles with optional raw producer metadata."""
    bundle = ctx.attr.bundle[XlsArtifactBundleInfo]
    fields = {
        "artifact_inputs": bundle.artifact_inputs,
        "driver": bundle.driver,
        "driver_supports_sv_enum_case_naming_policy": bundle.driver_supports_sv_enum_case_naming_policy,
        "driver_supports_sv_struct_field_ordering": bundle.driver_supports_sv_struct_field_ordering,
        "dslx_stdlib": bundle.dslx_stdlib,
        "dslx_stdlib_path": bundle.dslx_stdlib_path,
        "libxls": bundle.libxls,
        "runtime_files": bundle.runtime_files,
        "runtime_library_path": bundle.runtime_library_path,
        "resolved_identity": bundle.resolved_identity,
        "tools_root": bundle.tools_root,
        "tools_path": bundle.tools_path,
    }
    if ctx.attr.xls_pin_kind:
        fields["xls_pin"] = struct(kind = ctx.attr.xls_pin_kind, value = ctx.attr.xls_pin_value)
    if ctx.attr.xlsynth_pin_kind:
        fields["xlsynth_crate_pin"] = struct(
            kind = ctx.attr.xlsynth_pin_kind,
            value = ctx.attr.xlsynth_pin_value,
        )
    return [
        XlsArtifactBundleInfo(**fields),
        DefaultInfo(files = ctx.attr.bundle[DefaultInfo].files),
    ]

_legacy_bundle = rule(
    implementation = _legacy_bundle_impl,
    attrs = {
        "bundle": attr.label(mandatory = True, providers = [XlsArtifactBundleInfo]),
        "xls_pin_kind": attr.string(),
        "xls_pin_value": attr.string(),
        "xlsynth_pin_kind": attr.string(),
        "xlsynth_pin_value": attr.string(),
    },
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
        xls_version = "v0.37.0",
        xlsynth_driver_version = "v0.32.0",
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
        xlsynth_driver_git_revision = _OTHER_UPPERCASE_GIT_REVISION,
    )
    git_test = name + "_git"

    # Verifies: Distinct Git producer revisions are normalized independently.
    # Catches: Swapped, copied, or noncanonical XLS/XLSynth producer identities.
    _selected_toolchain_test(
        name = git_test,
        target_under_test = "//sample:" + name + "_git_library",
        expected_xls_kind = "git_revision",
        expected_xls_value = _UPPERCASE_GIT_REVISION.lower(),
        expected_driver_kind = "git_revision",
        expected_driver_value = _OTHER_UPPERCASE_GIT_REVISION.lower(),
    )

    mixed_bundle = name + "_mixed_bundle"
    _fake_bundle(
        name = mixed_bundle,
        xls_version = "0.40.0",
        xlsynth_driver_git_revision = _OTHER_UPPERCASE_GIT_REVISION,
    )
    mixed_test = name + "_mixed"

    # Verifies: XLS release and XLSynth Git producer identities remain independent.
    # Catches: Assuming both configured producers must share one identity kind.
    _selected_toolchain_test(
        name = mixed_test,
        target_under_test = "//sample:" + name + "_mixed_library",
        expected_xls_kind = "release_tag",
        expected_xls_value = "v0.40.0",
        expected_driver_kind = "git_revision",
        expected_driver_value = _OTHER_UPPERCASE_GIT_REVISION.lower(),
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

    legacy_bundle = name + "_legacy_bundle"
    _legacy_bundle(
        name = legacy_bundle,
        bundle = ":" + unpinned_bundle,
        visibility = ["//sample:__pkg__"],
    )
    legacy_test = name + "_legacy"

    # Verifies: Older externally constructed bundles remain valid overrides.
    # Catches: Treating newly introduced optional producer fields as mandatory.
    _selected_toolchain_test(
        name = legacy_test,
        target_under_test = "//sample:" + name + "_legacy_library",
        expect_missing = True,
    )

    external_bundle = name + "_external_bundle"
    _legacy_bundle(
        name = external_bundle,
        bundle = ":" + unpinned_bundle,
        visibility = ["//sample:__pkg__"],
        xls_pin_kind = "release_tag",
        xls_pin_value = "0.40.0",
        xlsynth_pin_kind = "git_revision",
        xlsynth_pin_value = _OTHER_UPPERCASE_GIT_REVISION,
    )
    external_test = name + "_external"

    # Verifies: External provider pins use the existing canonical producer parser.
    # Catches: Unprefixed releases or uppercase Git revisions leaking into metadata.
    _selected_toolchain_test(
        name = external_test,
        target_under_test = "//sample:" + name + "_external_library",
        expected_xls_kind = "release_tag",
        expected_xls_value = "v0.40.0",
        expected_driver_kind = "git_revision",
        expected_driver_value = _OTHER_UPPERCASE_GIT_REVISION.lower(),
    )

    invalid_external_bundle = name + "_invalid_external_bundle"
    _legacy_bundle(
        name = invalid_external_bundle,
        bundle = ":" + unpinned_bundle,
        tags = ["manual"],
        visibility = ["//sample:__pkg__"],
        xls_pin_kind = "git_revision",
        xls_pin_value = "ABC",
    )
    invalid_external_test = name + "_invalid_external"

    # Negative test: Invalid external Git pins fail at the bundle ingress boundary.
    _invalid_pin_test(
        name = invalid_external_test,
        target_under_test = "//sample:" + name + "_invalid_external_library",
        expected_error = "Expected exact 40-character Git revision",
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

    invalid_xls_release_bundle = name + "_invalid_xls_release_bundle"
    _fake_bundle(
        name = invalid_xls_release_bundle,
        tags = ["manual"],
        xls_version = "next",
    )
    invalid_xls_release_test = name + "_invalid_xls_release"

    # Negative test: Nonsemantic XLS release tags exercise producer error handling.
    _invalid_pin_test(
        name = invalid_xls_release_test,
        target_under_test = ":" + invalid_xls_release_bundle,
        expected_error = "Expected XLS semantic release tag",
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

    nonhex_revision_bundle = name + "_nonhex_revision_bundle"
    _fake_bundle(
        name = nonhex_revision_bundle,
        tags = ["manual"],
        xls_git_revision = "G" * 40,
    )
    nonhex_revision_test = name + "_nonhex_revision"

    # Negative test: Exact-length nonhex Git revisions exercise error handling.
    _invalid_pin_test(
        name = nonhex_revision_test,
        target_under_test = ":" + nonhex_revision_bundle,
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
            ":" + mixed_test,
            ":" + unpinned_test,
            ":" + legacy_test,
            ":" + external_test,
            ":" + invalid_external_test,
            ":" + invalid_release_test,
            ":" + invalid_xls_release_test,
            ":" + invalid_revision_test,
            ":" + nonhex_revision_test,
            ":" + ambiguous_test,
        ],
    )
