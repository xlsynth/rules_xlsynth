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


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"Please set {name} environment variable")
    return v


def _build_toolchain_toml(tool_dir: str) -> str:
    dslx_stdlib_path = os.path.join(tool_dir, "xls", "dslx", "stdlib")
    additional_dslx_paths = os.environ.get("XLSYNTH_DSLX_PATH", "").strip()
    additional_dslx_paths_list = additional_dslx_paths.split(":") if additional_dslx_paths else []

    enable_warnings = os.environ.get("XLSYNTH_DSLX_ENABLE_WARNINGS", "").strip()
    enable_warnings_list = enable_warnings.split(",") if enable_warnings else []

    disable_warnings = os.environ.get("XLSYNTH_DSLX_DISABLE_WARNINGS", "").strip()
    disable_warnings_list = disable_warnings.split(",") if disable_warnings else []

    use_system_verilog = os.environ.get("XLSYNTH_USE_SYSTEM_VERILOG", "").strip()
    use_system_verilog_toml = _bool_env_to_toml("XLSYNTH_USE_SYSTEM_VERILOG", use_system_verilog) if use_system_verilog != "" else None

    gate_format = os.environ.get("XLSYNTH_GATE_FORMAT", "").strip()
    assert_format = os.environ.get("XLSYNTH_ASSERT_FORMAT", "").strip()

    type_inference_v2 = os.environ.get("XLSYNTH_TYPE_INFERENCE_V2", "false").strip()
    type_inference_v2_toml = _bool_env_to_toml("XLSYNTH_TYPE_INFERENCE_V2", type_inference_v2)

    add_invariant_assertions = os.environ.get("XLSYNTH_ADD_INVARIANT_ASSERTIONS", "").strip()
    add_invariant_assertions_toml = _bool_env_to_toml("XLSYNTH_ADD_INVARIANT_ASSERTIONS", add_invariant_assertions) if add_invariant_assertions != "" else None

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
    if gate_format:
        lines.append(f"gate_format = {repr(gate_format)}")
    if assert_format:
        lines.append(f"assert_format = {repr(assert_format)}")
    if use_system_verilog_toml is not None:
        lines.append(f"use_system_verilog = {use_system_verilog_toml}")
    if add_invariant_assertions_toml is not None:
        lines.append(f"add_invariant_assertions = {add_invariant_assertions_toml}")

    return "\n".join(lines) + "\n"


def _consume_stdout_out(args: List[str]) -> Tuple[List[str], Optional[str]]:
    out_path: Optional[str] = None
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--stdout_out":
            # Capture next token as path if present
            if i + 1 < len(args):
                out_path = args[i + 1]
                i += 2
                continue
        cleaned.append(args[i])
        i += 1
    return cleaned, out_path


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
    passthrough, stdout_out_in_args = _consume_stdout_out(passthrough)
    stdout_out = args.stdout_out or stdout_out_in_args

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
    passthrough, stdout_out_in_args = _consume_stdout_out(passthrough)
    stdout_out = args.stdout_out or stdout_out_in_args

    if args.tool == "dslx_interpreter_main":
        stdlib = os.path.join(tools_dir, "xls", "dslx", "stdlib")
        extra: List[str] = [
            "--compare=jit",
            "--alsologtostderr",
            f"--dslx_stdlib_path={stdlib}",
        ]
        add_path = os.environ.get("XLSYNTH_DSLX_PATH", "").strip()
        if add_path:
            extra.append(f"--dslx_path={add_path}")
        enable_w = os.environ.get("XLSYNTH_DSLX_ENABLE_WARNINGS", "").strip()
        if enable_w:
            extra.append(f"--enable_warnings={enable_w}")
        disable_w = os.environ.get("XLSYNTH_DSLX_DISABLE_WARNINGS", "").strip()
        if disable_w:
            extra.append(f"--disable_warnings={disable_w}")
        tiv2 = os.environ.get("XLSYNTH_TYPE_INFERENCE_V2", "").strip()
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
        add_path = os.environ.get("XLSYNTH_DSLX_PATH", "").strip()
        if add_path:
            extra.append(f"--dslx_path={add_path}")
        passthrough = extra + passthrough
    elif args.tool == "typecheck_main":
        stdlib = os.path.join(tools_dir, "xls", "dslx", "stdlib")
        extra: List[str] = [
            f"--dslx_stdlib_path={stdlib}",
        ]
        add_path = os.environ.get("XLSYNTH_DSLX_PATH", "").strip()
        if add_path:
            extra.append(f"--dslx_path={add_path}")
        enable_w = os.environ.get("XLSYNTH_DSLX_ENABLE_WARNINGS", "").strip()
        if enable_w:
            extra.append(f"--enable_warnings={enable_w}")
        disable_w = os.environ.get("XLSYNTH_DSLX_DISABLE_WARNINGS", "").strip()
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
    p_driver.add_argument("passthrough", nargs=argparse.REMAINDER)
    p_driver.add_argument("--stdout_out", metavar="PATH")
    p_driver.set_defaults(func=_driver)

    p_tool = sub.add_parser("tool")
    p_tool.add_argument("tool")
    p_tool.add_argument("passthrough", nargs=argparse.REMAINDER)
    p_tool.add_argument("--stdout_out", metavar="PATH")
    p_tool.set_defaults(func=_tool)

    args = parser.parse_args(argv[1:])
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
