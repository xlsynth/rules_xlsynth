"""Analysis tests for the trusted resolved-identity construction boundary."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//:xls_toolchain.bzl", "XlsRuntimeSurfaceInfo", "xlsynth_driver_binary")

def _fake_runtime_impl(ctx):
    artifact = ctx.file.artifact
    return [
        XlsRuntimeSurfaceInfo(
            artifact_inputs = [artifact],
            dslx_stdlib = artifact,
            dslx_stdlib_path = artifact.path,
            libxls = artifact,
            runtime_files = [],
            runtime_library_path = artifact.dirname,
            tools_root = artifact,
            tools_path = artifact.dirname,
            xls_aot_runtime = None,
        ),
        DefaultInfo(files = depset([artifact])),
    ]

_fake_runtime = rule(
    implementation = _fake_runtime_impl,
    attrs = {
        "artifact": attr.label(allow_single_file = True, mandatory = True),
    },
)

def _forged_identity_is_rejected_impl(ctx):
    env = analysistest.begin(ctx)
    asserts.expect_failure(
        env,
        "trusted resolved identity requires an extension-generated *_toolchain repository",
    )
    return analysistest.end(env)

_forged_identity_is_rejected_test = analysistest.make(
    _forged_identity_is_rejected_impl,
    expect_failure = True,
)

def trusted_identity_boundary_test_suite(name):
    """Instantiates the trusted identity boundary analysis test.

    Args:
      name: Test target name.
    """
    runtime_name = name + "_runtime"
    driver_name = name + "_driver"
    _fake_runtime(
        name = runtime_name,
        artifact = "//:LICENSE",
    )
    xlsynth_driver_binary(
        name = driver_name,
        action_path = "/usr/bin",
        artifact_source = "download_only",
        resolved_identity = "//:LICENSE",
        runtime = ":" + runtime_name,
    )
    _forged_identity_is_rejected_test(
        name = name,
        target_under_test = ":" + driver_name,
    )
