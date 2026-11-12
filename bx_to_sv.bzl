# SPDX-License-Identifier: Apache-2.0

"""Convenience macro for emitting SystemVerilog from BX."""

load(":block_ir_to_sv.bzl", "block_ir_to_sv")
load(":bx_to_ir.bzl", "bx_to_ir")

def bx_to_sv(
        name,
        *,
        lib,
        top,
        link_ir = None,
        reset_active_low = False,
        reset_asynchronous = False,
        warnings_as_errors = True,
        lower_ir = True,
        module_name = "",
        xls_bundle = None,
        **kwargs):
    """Compiles a BX design and emits a SystemVerilog file.

    Args:
      name: Name of the SystemVerilog target.
      lib: Root bx_library.
      top: Top block name.
      link_ir: Optional package containing the BX extern implementations.
      reset_active_low: Whether the BX hierarchy uses active-low reset.
      reset_asynchronous: Whether the BX hierarchy uses asynchronous reset.
      warnings_as_errors: Whether BX warnings fail compilation.
      lower_ir: Whether to inline function calls and maps and unroll counted loops before emission.
      module_name: Optional override for the emitted top module name.
      xls_bundle: Optional XLS bundle override for both actions.
      **kwargs: Common Bazel attributes for the emitted target.
    """
    ir_name = name + "_block_ir"
    ir_attrs = {
        key: kwargs[key]
        for key in [
            "compatible_with",
            "exec_compatible_with",
            "exec_properties",
            "features",
            "restricted_to",
            "tags",
            "target_compatible_with",
            "testonly",
        ]
        if key in kwargs
    }
    bx_to_ir(
        name = ir_name,
        lib = lib,
        top = top,
        link_ir = link_ir,
        reset_active_low = reset_active_low,
        reset_asynchronous = reset_asynchronous,
        warnings_as_errors = warnings_as_errors,
        xls_bundle = xls_bundle,
        visibility = ["//visibility:private"],
        **ir_attrs
    )
    block_ir_to_sv(
        name = name,
        ir = ":" + ir_name,
        lower_ir = lower_ir,
        module_name = module_name,
        xls_bundle = xls_bundle,
        **kwargs
    )
