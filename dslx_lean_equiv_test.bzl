# SPDX-License-Identifier: Apache-2.0
"""Lean equivalence tests for optimized DSLX functions."""

load(":dslx_to_ir.bzl", "dslx_to_ir")
load(":ir_fn_lean_equiv_test.bzl", "ir_fn_lean_equiv_test")

def dslx_lean_equiv_test(name, lhs, lhs_top, rhs, rhs_top, proof, proof_srcs = [], xls_bundle = None, **kwargs):
    """Lowers two DSLX functions and checks a Lean proof of their equivalence.

    Args:
      name: Name of the Bazel test.
      lhs: Left DSLX library.
      lhs_top: Function name in the left DSLX module.
      rhs: Right DSLX library.
      rhs_top: Function name in the right DSLX module.
      proof: Lean proof term for the generated Target.Equivalent.
      proof_srcs: Lean helper modules imported by the proof.
      xls_bundle: Optional bundle for the proof driver and Lean. DSLX lowering
        uses the registered XLS toolchain.
      **kwargs: Common Bazel test attributes.
    """
    for side, lib, top in [("lhs", lhs, lhs_top), ("rhs", rhs, rhs_top)]:
        dslx_to_ir(
            name = name + "_" + side + "_ir",
            lib = lib,
            top = top,
            tags = ["manual"],
            target_compatible_with = kwargs.get("target_compatible_with", []),
            testonly = True,
            visibility = ["//visibility:private"],
        )
    ir_fn_lean_equiv_test(
        name = name,
        lhs = ":" + name + "_lhs_ir",
        rhs = ":" + name + "_rhs_ir",
        proof = proof,
        proof_srcs = proof_srcs,
        xls_bundle = xls_bundle,
        **kwargs
    )
