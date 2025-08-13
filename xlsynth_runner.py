#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple


def _bool_env_to_toml(name: str, val: str) -> Optional[str]:
    v = val.strip()
    if v == "":
        return None
    if v not in ("true", "false"):
        raise ValueError(f"Invalid value for {name}: {val}")
    return v


def _get_env(name: str) -> Optional[str]:
    return os.environ.get(name, "").strip()


def _require_env(name: str) -> str:
    v = _get_env(name)
    if not v:
        raise RuntimeError(f"Please set {name} environment variable")
    return v


def _get_env_list(name: str, separator: str) -> List[str]:
    v = _get_env(name)
    return v.split(separator) if v else []


def _get_bool_toml_from_env(name: str) -> Optional[str]:
    v = _get_env(name)
    return _bool_env_to_toml(name, v) if v != "" else None


def _toml_lines_from_regular_envs(pairs: List[Tuple[str, str]]) -> List[str]:
    lines: List[str] = []
    for env_name, toml_key in pairs:
        v = _get_env(env_name)
        if v:
            lines.append(f"{toml_key} = {repr(v)}")
    return lines


def _toml_lines_from_bool_envs(pairs: List[Tuple[str, str]]) -> List[str]:
    lines: List[str] = []
    for env_name, toml_key in pairs:
        b = _get_bool_toml_from_env(env_name)
        if b is not None:
            lines.append(f"{toml_key} = {b}")
    return lines


def _build_toolchain_toml(tool_dir: str) -> str:
    dslx_stdlib_path = os.path.join(tool_dir, "xls", "dslx", "stdlib")

    additional_dslx_paths_list = _get_env_list("XLSYNTH_DSLX_PATH", ":")
    enable_warnings_list = _get_env_list("XLSYNTH_DSLX_ENABLE_WARNINGS", ",")
    disable_warnings_list = _get_env_list("XLSYNTH_DSLX_DISABLE_WARNINGS", ",")

    tiv2_env = _get_env("XLSYNTH_TYPE_INFERENCE_V2")
    # Default to false when unset
    type_inference_v2_toml = _bool_env_to_toml("XLSYNTH_TYPE_INFERENCE_V2", tiv2_env if tiv2_env != "" else "false")

    codegen_regular_envs: List[Tuple[str, str]] = [
        ("XLSYNTH_GATE_FORMAT", "gate_format"),
        ("XLSYNTH_ASSERT_FORMAT", "assert_format"),
    ]
    codegen_bool_envs: List[Tuple[str, str]] = [
        ("XLSYNTH_USE_SYSTEM_VERILOG", "use_system_verilog"),
        ("XLSYNTH_ADD_INVARIANT_ASSERTIONS", "add_invariant_assertions"),
    ]

    lines: List[str] = []
    lines.append("[toolchain]")
    lines.append(f"tool_path = \"{tool_dir}\"")
    lines.append("")
    lines.append("[toolchain.dslx]")
    lines.append(f"dslx_stdlib_path = \"{dslx_stdlib_path}\"")
    lines.append(f"dslx_path = {repr(additional_dslx_paths_list)}")
    lines.append(f"enable_warnings = {repr(enable_warnings_list)}")
    lines.append(f"disable_warnings = {repr(disable_warnings_list)}")
    lines.append(f"type_inference_v2 = {type_inference_v2_toml}")
    lines.append("")
    lines.append("[toolchain.codegen]")
    lines.extend(_toml_lines_from_regular_envs(codegen_regular_envs))
    lines.extend(_toml_lines_from_bool_envs(codegen_bool_envs))

    return "\n".join(lines) + "\n"

def _run(cmd: List[str], stdout_out: Optional[str]) -> int:
    if stdout_out:
        with open(stdout_out, "wb") as f:
            proc = subprocess.run(cmd, stdout=f, check=False)
            return proc.returncode
    else:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode


def _driver(args: argparse.Namespace) -> int:
    tools_dir = _require_env("XLSYNTH_TOOLS")
    driver_dir = _require_env("XLSYNTH_DRIVER_DIR")
    driver_path = os.path.join(driver_dir, "xlsynth-driver")
    passthrough = list(args.passthrough)
    stdout_out = args.stdout_out

    toml = _build_toolchain_toml(tools_dir)
    with tempfile.NamedTemporaryFile("w", delete=False, prefix="xlsynth_toolchain_", suffix=".toml") as tf:
        tf.write(toml)
        toolchain_path = tf.name
    try:
        cmd = [driver_path, f"--toolchain={toolchain_path}", args.subcommand, *passthrough]
        return _run(cmd, stdout_out)
    finally:
        try:
            os.unlink(toolchain_path)
        except OSError:
            pass


def _tool(args: argparse.Namespace) -> int:
    tools_dir = _require_env("XLSYNTH_TOOLS")
    tool_path = os.path.join(tools_dir, args.tool)
    passthrough = list(args.passthrough)
    stdout_out = args.stdout_out

    if args.tool == "dslx_interpreter_main":
        stdlib = os.path.join(tools_dir, "xls", "dslx", "stdlib")
        extra: List[str] = [
            "--compare=jit",
            "--alsologtostderr",
            f"--dslx_stdlib_path={stdlib}",
        ]
        add_path = _get_env("XLSYNTH_DSLX_PATH") or ""
        if add_path:
            extra.append(f"--dslx_path={add_path}")
        enable_w = _get_env("XLSYNTH_DSLX_ENABLE_WARNINGS") or ""
        if enable_w:
            extra.append(f"--enable_warnings={enable_w}")
        disable_w = _get_env("XLSYNTH_DSLX_DISABLE_WARNINGS") or ""
        if disable_w:
            extra.append(f"--disable_warnings={disable_w}")
        tiv2 = _get_env("XLSYNTH_TYPE_INFERENCE_V2") or ""
        if tiv2 == "true":
            extra.append("--type_inference_v2=true")
        elif tiv2 in ("", "false"):
            pass
        else:
            raise ValueError("Invalid value for XLSYNTH_TYPE_INFERENCE_V2: " + tiv2)
        passthrough = extra + passthrough
    elif args.tool == "prove_quickcheck_main":
        stdlib = os.path.join(tools_dir, "xls", "dslx", "stdlib")
        extra = [
            "--alsologtostderr",
            f"--dslx_stdlib_path={stdlib}",
        ]
        add_path = _get_env("XLSYNTH_DSLX_PATH") or ""
        if add_path:
            extra.append(f"--dslx_path={add_path}")
        passthrough = extra + passthrough
    elif args.tool == "typecheck_main":
        stdlib = os.path.join(tools_dir, "xls", "dslx", "stdlib")
        extra: List[str] = [
            f"--dslx_stdlib_path={stdlib}",
        ]
        add_path = _get_env("XLSYNTH_DSLX_PATH") or ""
        if add_path:
            extra.append(f"--dslx_path={add_path}")
        enable_w = _get_env("XLSYNTH_DSLX_ENABLE_WARNINGS") or ""
        if enable_w:
            extra.append(f"--enable_warnings={enable_w}")
        disable_w = _get_env("XLSYNTH_DSLX_DISABLE_WARNINGS") or ""
        if disable_w:
            extra.append(f"--disable_warnings={disable_w}")
        passthrough = extra + passthrough

    cmd = [tool_path, *passthrough]
    return _run(cmd, stdout_out)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="xlsynth_runner")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_driver = sub.add_parser("driver")
    p_driver.add_argument("subcommand")
    p_driver.add_argument("--stdout_out", metavar="PATH")
    p_driver.set_defaults(func=_driver)

    p_tool = sub.add_parser("tool")
    p_tool.add_argument("tool")
    p_tool.add_argument("--stdout_out", metavar="PATH")
    p_tool.set_defaults(func=_tool)

    args, unknown = parser.parse_known_args(argv[1:])
    # Treat any unrecognized arguments as passthrough to the underlying tool/driver subcommand
    setattr(args, "passthrough", unknown)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
