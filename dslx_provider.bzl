# SPDX-License-Identifier: Apache-2.0

"""Exposes DSLX source dependencies and each library's declared toolchain pins."""

load(":env_helpers.bzl", "python_runner_source")
load(
    ":xls_toolchain.bzl",
    "XlsArtifactBundleInfo",
    "declare_xls_toolchain_toml",
    "get_selected_tools_toolchain",
    "get_tool_artifact_inputs",
    "normalize_selected_producer_pin",
)

DslxInfo = provider(
    doc = "A DSLX root module and its complete source inputs, independently of ordering.",
    fields = {
        "root": "The File containing this library's root module.",
        "transitive_srcs": "A depset of direct and transitive source Files, including root. Order has no semantic meaning.",
    },
)

DslxSelectedToolchainInfo = provider(
    doc = "Declared, unauthenticated producer pins selected by one DSLX library.",
    fields = {
        "metadata": "Opt-in JSON artifact containing the declared selected producer pins.",
        "xls_pin": "Declared XLS producer struct with .kind and .value, or None when unavailable.",
        "xlsynth_crate_pin": "Declared XLSynth producer struct with .kind and .value, or None when unavailable.",
    },
)

def _dslx_library_impl(ctx):
    """Resolves the root once and propagates its source closure to consumers."""
    direct_srcs = depset(ctx.files.srcs).to_list()
    if ctx.file.root:
        root = ctx.file.root
        if root not in direct_srcs:
            fail("root must be one of the direct srcs", attr = "root")
    elif len(direct_srcs) == 1:
        root = direct_srcs[0]
    else:
        fail("must specify root when srcs does not contain exactly one file", attr = "root")

    dslx_info = DslxInfo(
        root = root,
        transitive_srcs = depset(
            direct = direct_srcs,
            transitive = [dep[DslxInfo].transitive_srcs for dep in ctx.attr.deps],
        ),
    )
    srcs = dslx_info.transitive_srcs.to_list()
    typecheck_output = ctx.actions.declare_file(ctx.label.name + ".typecheck")

    # Run typechecking via the embedded runner so env is read at action runtime.
    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source(), is_executable = True)
    toolchain = get_selected_tools_toolchain(ctx)
    toolchain_file = declare_xls_toolchain_toml(ctx, name = "typecheck", toolchain = toolchain)
    action_inputs = srcs + [toolchain_file] + get_tool_artifact_inputs(toolchain, "typecheck_main")
    ctx.actions.run(
        inputs = action_inputs,
        outputs = [typecheck_output],
        executable = runner,
        arguments = [
            "tool",
            "--toolchain",
            toolchain_file.path,
            "--runtime_library_path",
            toolchain.runtime_library_path,
            "typecheck_main",
            root.path,
            "--output_path",
            typecheck_output.path,
        ],
        use_default_shell_env = False,
    )

    xls_pin = normalize_selected_producer_pin(
        getattr(toolchain, "xls_pin", None),
        "XLS pin",
        require_xls_release = True,
    )
    xlsynth_crate_pin = normalize_selected_producer_pin(
        getattr(toolchain, "xlsynth_crate_pin", None),
        "XLSynth crate pin",
    )
    selected_toolchain_metadata = ctx.actions.declare_file(ctx.label.name + ".selected_toolchain.json")
    ctx.actions.write(
        output = selected_toolchain_metadata,
        content = json.encode({
            "schema_version": 1,
            "xls_pin": xls_pin,
            "xlsynth_crate_pin": xlsynth_crate_pin,
        }) + "\n",
    )

    return [
        dslx_info,
        DefaultInfo(files = depset([typecheck_output])),
        DslxSelectedToolchainInfo(
            metadata = selected_toolchain_metadata,
            xls_pin = xls_pin,
            xlsynth_crate_pin = xlsynth_crate_pin,
        ),
        OutputGroupInfo(selected_toolchain = depset([selected_toolchain_metadata])),
    ]

dslx_library = rule(
    doc = "Define a DSLX module.",
    implementation = _dslx_library_impl,
    attrs = {
        "deps": attr.label_list(
            doc = "The list of other libraries to be linked.",
            providers = [
                DslxInfo,
            ],
        ),
        "srcs": attr.label_list(
            doc = "DSLX source inputs. Order is not significant; set root when there is more than one file.",
            allow_files = [".x"],
        ),
        "root": attr.label(
            doc = "Root DSLX module, selected from srcs. May be omitted only for a single-source library.",
            allow_single_file = [".x"],
        ),
        "xls_bundle": attr.label(
            doc = "Optional XLS bundle override.",
            providers = [XlsArtifactBundleInfo],
        ),
    },
    toolchains = ["//:toolchain_type"],
)
