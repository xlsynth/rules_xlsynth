# SPDX-License-Identifier: Apache-2.0

IrInfo = provider(
    doc = "Contains raw and optimized XLS IR packages for a DSLX function or proc. Consumers determine which entity kinds they support.",
    fields = {
        "ir_file": "The unoptimized IR package, including its converter-selected entrypoint.",
        "opt_ir_file": "The optimized IR package; optimization may transform the function or proc network.",
    },
)
