# SPDX-License-Identifier: Apache-2.0

DslxInfo = provider(
    doc = "Contains DAG info per node in a struct.",
    fields = {
        "dag": "A depset of the DAG entries to propagate upwards.",
    },
)

def make_dag_entry(srcs, deps, label):
    return struct(
        srcs = tuple(srcs),
        deps = tuple(deps),
        label = label,
    )

def make_dslx_info(
        new_entries = (),
        old_infos = ()):
    return DslxInfo(
        dag = depset(
            direct = new_entries,
            order = "postorder",
            transitive = [x.dag for x in old_infos],
        ),
    )

def _dslx_library_impl(ctx):
    """Produces a DAG for the given target.

    Args:
      ctx: The context for this rule.

    Returns:
      A struct containing the DAG at this level of the dependency graph.
    """
    dslx_info = make_dslx_info(
        new_entries = [make_dag_entry(
            srcs = ctx.files.srcs,
            deps = ctx.attr.deps,
            label = ctx.label,
        )],
        old_infos = [dep[DslxInfo] for dep in ctx.attr.deps],
    )

    return [
        dslx_info,
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
            doc = "DSLX sources.",
            allow_files = [".x"],
        ),
    },
)
