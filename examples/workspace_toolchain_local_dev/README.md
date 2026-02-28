# Local XLS development workspace

This workspace documents the `artifact_source = "local_paths"` flow. It points
`rules_xlsynth` at a fixed `/tmp/xls-local-dev/` staging tree instead of using
artifact-path `.bazelrc` flags.

Expected layout:

```text
/tmp/xls-local-dev/
|-- bin/
|   `-- xlsynth-driver
|-- libxls.so
|-- tools/
|   |-- check_ir_equivalence_main
|   |-- codegen_main
|   |-- delay_info_main
|   |-- dslx_fmt
|   |-- dslx_interpreter_main
|   |-- ir_converter_main
|   |-- opt_main
|   |-- prove_quickcheck_main
|   `-- typecheck_main
`-- xls/dslx/stdlib/
    `-- std.x
```

`local_tools_path` must be the directory that directly contains the XLS tool
binaries, and `local_dslx_stdlib_path` must be the directory that directly
contains `std.x`.

Populate that tree by copying or symlinking outputs from local XLS and
`xlsynth-driver` builds. A typical setup stages the compiled tool binaries into
`/tmp/xls-local-dev/tools`, points `xlsynth-driver` at
`/tmp/xls-local-dev/bin/xlsynth-driver`, and places the matching shared library
at `/tmp/xls-local-dev/libxls.so`.

On macOS, update `MODULE.bazel` to use `/tmp/xls-local-dev/libxls.dylib`
instead of `/tmp/xls-local-dev/libxls.so`.

After the staging tree exists, run:

```bash
bazel build //:smoke_sv_types //:smoke_pipeline
```

`examples/workspace_toolchain_smoke/` shows the same rule surface with one
registered default bundle and one explicit `xls_bundle` override. This local
development variant keeps the BUILD file minimal and pushes all artifact
selection into `MODULE.bazel`.
