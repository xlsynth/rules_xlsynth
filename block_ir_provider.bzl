# SPDX-License-Identifier: Apache-2.0

"""Provider for a package containing XLS blocks."""

BlockIrInfo = provider(
    doc = "Contains a package-form XLS block IR artifact and its selected top.",
    fields = {
        "ir_file": "The block IR file.",
        "top": "The selected block name.",
    },
)
