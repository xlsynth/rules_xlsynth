#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import argparse
import ast
import os
import subprocess
import sys
from enum import Enum
from typing import Any, Dict, List, NamedTuple


_TOOL_CONFIG = {
    "dslx_interpreter_main": {
        "base_flags": ["--compare=jit", "--alsologtostderr"],
        "dslx_config": True,
        "dslx_scalar_settings": [],
    },
    "prove_quickcheck_main": {
        "base_flags": ["--alsologtostderr"],
        "dslx_config": True,
        "dslx_scalar_settings": [],
    },
    "typecheck_main": {
        "base_flags": [],
        "dslx_config": True,
        "dslx_scalar_settings": [],
    },
    "dslx_fmt": {
        "base_flags": [],
        "dslx_config": False,
        "dslx_scalar_settings": [],
    },
}


class EnvFlagMode(Enum):
    PASSTHROUGH_IF_NONEMPTY = "passthrough_if_nonempty"


class EnvFlagSpec(NamedTuple):
    flag_name: str
    mode: EnvFlagMode


_DSLX_FLAG_SPECS: Dict[str, EnvFlagSpec] = {
    "dslx_path":
    EnvFlagSpec("dslx_path", EnvFlagMode.PASSTHROUGH_IF_NONEMPTY),
    "enable_warnings":
    EnvFlagSpec("enable_warnings", EnvFlagMode.PASSTHROUGH_IF_NONEMPTY),
    "disable_warnings":
    EnvFlagSpec("disable_warnings", EnvFlagMode.PASSTHROUGH_IF_NONEMPTY),
    "type_inference_v2":
    EnvFlagSpec("type_inference_v2", EnvFlagMode.PASSTHROUGH_IF_NONEMPTY),
}


def _setting_flag_builder(setting_name: str, value: str) -> List[str]:
    spec = _DSLX_FLAG_SPECS.get(setting_name)
    if not spec:
        return []

    if spec.mode == EnvFlagMode.PASSTHROUGH_IF_NONEMPTY:
        return [f"--{spec.flag_name}={value}"] if value else []

    return []


def _parse_scalar(value_text: str) -> Any:
    if value_text == "true":
        return True
    if value_text == "false":
        return False
    return ast.literal_eval(value_text)


def _parse_toolchain_toml(path: str) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    section_stack: List[str] = []
    with open(path, "r", encoding = "utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section_stack = line[1:-1].split(".")
                continue
            key, value_text = line.split("=", 1)
            key = key.strip()
            value_text = value_text.strip()
            target = parsed
            for section_name in section_stack:
                target = target.setdefault(section_name, {})
            target[key] = _parse_scalar(value_text)
    return parsed


def _toolchain_dslx_config(toolchain_data: Dict[str, Any]) -> Dict[str, Any]:
    toolchain_section = toolchain_data.get("toolchain", {})
    return toolchain_section.get("dslx", {})


def _runfiles_roots() -> List[str]:
    roots: List[str] = []
    for env_var in ["RUNFILES_DIR", "TEST_SRCDIR"]:
        value = os.environ.get(env_var)
        if value and value not in roots:
            roots.append(value)
    return roots


def _runfiles_candidates(path: str) -> List[str]:
    candidates = [path]
    for marker in ["external/", "_main/"]:
        marker_index = path.find(marker)
        if marker_index != -1:
            candidate = path[marker_index + len(marker):]
            if candidate not in candidates:
                candidates.append(candidate)
            prefixed = "_main/" + candidate
            if prefixed not in candidates:
                candidates.append(prefixed)
    return candidates


def _resolve_runtime_path(path: str) -> str:
    if not path or os.path.isabs(path):
        return path

    for root in _runfiles_roots():
        for candidate in _runfiles_candidates(path):
            resolved = os.path.join(root, candidate)
            if os.path.exists(resolved):
                return resolved
    return path


def _resolve_executable_path(path: str) -> str:
    return _resolve_runtime_path(path)


def _build_extra_args_for_tool(tool: str, toolchain_data: Dict[str, Any]) -> List[str]:
    cfg = _TOOL_CONFIG.get(tool)
    if not cfg:
        return []
    toolchain_section = toolchain_data.get("toolchain", {})
    dslx_cfg = _toolchain_dslx_config(toolchain_data)
    stdlib = _resolve_runtime_path(dslx_cfg.get("dslx_stdlib_path", ""))
    if not stdlib:
        raise RuntimeError("Toolchain TOML is missing toolchain.dslx.dslx_stdlib_path")
    extra: List[str] = [f"--dslx_stdlib_path={stdlib}"]
    extra.extend(cfg.get("base_flags", []))
    if cfg.get("dslx_config"):
        list_settings = [
            ("dslx_path", ":"),
            ("enable_warnings", ","),
            ("disable_warnings", ","),
        ]
        for setting_name, separator in list_settings:
            values = dslx_cfg.get(setting_name, [])
            joined = separator.join(values)
            extra.extend(_setting_flag_builder(setting_name, joined))
        for setting_name in cfg.get("dslx_scalar_settings", []):
            setting_value = dslx_cfg.get(setting_name)
            if setting_value is not None:
                extra.extend(_setting_flag_builder(
                    setting_name,
                    "true" if setting_value else "false",
                ))
    return extra


def _run_subprocess(
        cmd: List[str],
        *,
        runtime_library_path: str,
        stdout_path: str) -> int:
    env = os.environ.copy()
    resolved_runtime_library_path = _resolve_runtime_path(runtime_library_path)
    if resolved_runtime_library_path:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = (
            resolved_runtime_library_path
            if not existing
            else resolved_runtime_library_path + os.pathsep + existing
        )
    stdout_handle = None
    stdout_stream = None
    if stdout_path:
        stdout_handle = open(stdout_path, "wb")
        stdout_stream = stdout_handle
    try:
        proc = subprocess.run(cmd, check = False, env = env, stdout = stdout_stream)
        return proc.returncode
    finally:
        if stdout_handle is not None:
            stdout_handle.close()


def _driver(args: argparse.Namespace) -> int:
    cmd = [
        _resolve_executable_path(args.driver_path),
        f"--toolchain={args.toolchain}",
        args.subcommand,
        *list(args.passthrough),
    ]
    return _run_subprocess(
        cmd,
        runtime_library_path = args.runtime_library_path,
        stdout_path = args.stdout_path,
    )


def _tool(args: argparse.Namespace) -> int:
    toolchain_data = _parse_toolchain_toml(args.toolchain)
    tool_path_root = toolchain_data.get("toolchain", {}).get("tool_path")
    if not tool_path_root:
        raise RuntimeError("Toolchain TOML is missing toolchain.tool_path")
    tool_path = _resolve_runtime_path(os.path.join(tool_path_root, args.tool))
    passthrough = list(args.passthrough)
    extra = _build_extra_args_for_tool(args.tool, toolchain_data)
    if extra:
        passthrough = extra + passthrough

    cmd = [tool_path, *passthrough]
    return _run_subprocess(
        cmd,
        runtime_library_path = args.runtime_library_path,
        stdout_path = args.stdout_path,
    )


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="xlsynth_runner", allow_abbrev=False)
    sub = parser.add_subparsers(dest="mode")

    # No global arguments; subcommands define their own.

    p_driver = sub.add_parser("driver")
    p_driver.add_argument("--driver_path", required=True)
    p_driver.add_argument("--runtime_library_path", default="")
    p_driver.add_argument("--stdout_path", default="")
    p_driver.add_argument("--toolchain", required=True)
    p_driver.add_argument("subcommand")
    p_driver.set_defaults(func=_driver)

    p_tool = sub.add_parser("tool")
    p_tool.add_argument("--runtime_library_path", default="")
    p_tool.add_argument("--stdout_path", default="")
    p_tool.add_argument("--toolchain", required=True)
    p_tool.add_argument("tool")
    p_tool.set_defaults(func=_tool)

    # We intentionally use parse_known_args so that only flags defined on the selected
    # subparser are consumed here. All remaining args are treated
    # as passthrough and forwarded verbatim to the underlying tool/driver subcommand.
    args, unknown = parser.parse_known_args(argv[1:])
    if args.mode is None:
        parser.print_usage()
        return 2
    # Treat any unrecognized arguments as passthrough to the underlying tool/driver subcommand.
    setattr(args, "passthrough", unknown)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
