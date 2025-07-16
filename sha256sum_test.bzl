# SPDX-License-Identifier: Apache-2.0
"""Simple Bazel test rule that fails if the SHA-256 checksum of a file differs from an expected value.

Usage:

load("//:sha256sum_test.bzl", "sha256sum_test")

sha256sum_test(
    name = "my_file_hash_test",
    src  = ":my_file",  # label providing exactly one file
    want = "<expected_sha256_hex>",
)
"""

load("@bazel_skylib//rules:build_test.bzl", "build_test")

# Implementation helper.

def _sha256sum_test_impl(ctx):
    src = ctx.file.src
    want = ctx.attr.want

    # Generate a small shell script that computes sha256sum and compares.
    script = ctx.actions.declare_file(ctx.label.name + ".sh")

    script_content = """#!/usr/bin/env bash
set -euo pipefail

# Bazel sets TEST_SRCDIR to the runfiles directory.
FILE="$TEST_SRCDIR/%s/%s"
actual=$(sha256sum "$FILE" | awk '{print $1}')
if [[ "$actual" != "%s" ]]; then
  echo "SHA256 mismatch for %s: got $actual, want %s" >&2
  exit 1
fi
""" % (ctx.workspace_name, src.short_path, want, src.short_path, want)

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    return DefaultInfo(
        executable = script,
        runfiles = ctx.runfiles(files = [src]),
        files = depset([script]),
    )

sha256sum_test = rule(
    implementation = _sha256sum_test_impl,
    test = True,
    attrs = {
        "src": attr.label(allow_single_file = True, mandatory = True),
        "want": attr.string(mandatory = True),
    },
)
