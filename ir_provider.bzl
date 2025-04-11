# SPDX-License-Identifier: Apache-2.0

IrInfo = provider(
    doc = "Contains IR files for a DSLX target.",
    fields = {
        "ir_file": "The unoptimized IR file.",
        "opt_ir_file": "The optimized IR file.",
    },
)
