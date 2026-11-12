# SPDX-License-Identifier: Apache-2.0

"""Declares the source inputs for BX compilation."""

load(":dslx_provider.bzl", "DslxInfo")

BxInfo = provider(
    doc = "The root module and source closure of a BX library.",
    fields = {
        "root": "The File containing the root BX module.",
        "transitive_srcs": "A depset of BX and DSLX source Files, including the root.",
    },
)

def _bx_library_impl(ctx):
    direct_srcs = depset(ctx.files.srcs)
    srcs = direct_srcs.to_list()
    for src in srcs:
        if src.is_directory or src.extension != "bx":
            fail("expected a .bx file, got {}".format(src.short_path), attr = "srcs")
    root = ctx.file.root
    if root:
        if root not in srcs:
            fail("root must be one of the direct srcs", attr = "root")
    elif len(srcs) == 1:
        root = srcs[0]
    else:
        fail("must specify root when srcs does not contain exactly one file", attr = "root")

    return [
        BxInfo(
            root = root,
            transitive_srcs = depset(
                transitive = [direct_srcs] +
                             [dep[BxInfo].transitive_srcs for dep in ctx.attr.deps] +
                             [dep[DslxInfo].transitive_srcs for dep in ctx.attr.dslx_deps],
            ),
        ),
        DefaultInfo(files = direct_srcs),
    ]

bx_library = rule(
    doc = "Declare a reusable BX source library for compilation, testing, and proofs.",
    implementation = _bx_library_impl,
    attrs = {
        "deps": attr.label_list(
            doc = "BX libraries available for imports.",
            providers = [BxInfo],
        ),
        "dslx_deps": attr.label_list(
            doc = "DSLX libraries available for imports.",
            providers = [DslxInfo],
        ),
        "root": attr.label(
            doc = "Root BX module selected from srcs. May be omitted for a single-source library.",
            allow_single_file = [".bx"],
        ),
        "srcs": attr.label_list(
            doc = "Direct BX source files.",
            allow_empty = False,
            allow_files = [".bx"],
            mandatory = True,
        ),
    },
    provides = [BxInfo],
)
