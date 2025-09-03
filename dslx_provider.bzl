# SPDX-License-Identifier: Apache-2.0

load(":env_helpers.bzl", "python_runner_source")

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

    typecheck_output = ctx.actions.declare_file(ctx.label.name + ".typecheck")

    dag_entries = []
    for dep in ctx.attr.deps:
        dag_entries.extend(dep[DslxInfo].dag.to_list())

    srcs = []
    for entry in dag_entries:
        srcs += [src for src in list(entry.srcs)]
    for src in ctx.files.srcs:
        srcs.append(src)

    # Run typechecking via the embedded runner so env is read at action runtime.
    runner = ctx.actions.declare_file(ctx.label.name + "_runner.py")
    ctx.actions.write(output = runner, content = python_runner_source())
    ctx.actions.run(
        inputs = srcs,
        outputs = [typecheck_output],
        executable = runner,
        arguments = [
            "tool",
            "typecheck_main",
            srcs[-1].path,
            "--output_path",
            typecheck_output.path,
        ],
        use_default_shell_env = True,
    )

    return [
        dslx_info,
        DefaultInfo(files = depset([typecheck_output])),
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
