def python_runner_source():
    """Returns the embedded xlsynth_runner.py source.

    The returned program reads XLSYNTH_* from the action execution environment
    and invokes either the driver (via the 'driver' subcommand) or a tool
    (via the 'tool' subcommand), forwarding passthrough flags accordingly.

    """
    return """#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import subprocess
import sys
import tempfile
from enum import Enum
from typing import List, Optional, Tuple, Dict, NamedTuple


def _bool_env_to_toml(name: str, val: str) -> Optional[str]:
    v = val.strip()
    if v == "":
        return None
    if v not in ("true", "false"):
        raise ValueError(f"Invalid value for {name}: {val}")
    return v


def _get_env(name: str) -> str:
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


# Declarative per-tool configuration for extra flags
_TOOL_CONFIG = {
    "dslx_interpreter_main": {
        "base_flags": ["--compare=jit", "--alsologtostderr"],
        "env_flags": [
            "XLSYNTH_DSLX_PATH",
            "XLSYNTH_DSLX_ENABLE_WARNINGS",
            "XLSYNTH_DSLX_DISABLE_WARNINGS",
        ],
    },
    "prove_quickcheck_main": {
        "base_flags": ["--alsologtostderr"],
        "env_flags": [
            "XLSYNTH_DSLX_PATH",
        ],
    },
    "typecheck_main": {
        "base_flags": [],
        "env_flags": [
            "XLSYNTH_DSLX_PATH",
            "XLSYNTH_DSLX_ENABLE_WARNINGS",
            "XLSYNTH_DSLX_DISABLE_WARNINGS",
        ],
    },
}


class EnvFlagMode(Enum):
    PASSTHROUGH_IF_NONEMPTY = "passthrough_if_nonempty"


class EnvFlagSpec(NamedTuple):
    flag_name: str
    mode: EnvFlagMode


# Declarative mapping from env var to flag-building behavior
_ENV_FLAG_SPECS: Dict[str, EnvFlagSpec] = {
    "XLSYNTH_DSLX_PATH":
    EnvFlagSpec("dslx_path", EnvFlagMode.PASSTHROUGH_IF_NONEMPTY),
    "XLSYNTH_DSLX_ENABLE_WARNINGS":
    EnvFlagSpec("enable_warnings", EnvFlagMode.PASSTHROUGH_IF_NONEMPTY),
    "XLSYNTH_DSLX_DISABLE_WARNINGS":
    EnvFlagSpec("disable_warnings", EnvFlagMode.PASSTHROUGH_IF_NONEMPTY),
}


def _env_flag_builder(env_name: str, value: str) -> List[str]:
    spec = _ENV_FLAG_SPECS.get(env_name)
    if not spec:
        return []

    if spec.mode == EnvFlagMode.PASSTHROUGH_IF_NONEMPTY:
        return [f"--{spec.flag_name}={value}"] if value else []

    return []


def _build_extra_args_for_tool(tool: str, tools_dir: str) -> List[str]:
    cfg = _TOOL_CONFIG.get(tool)
    if not cfg:
        return []
    stdlib = os.path.join(tools_dir, "xls", "dslx", "stdlib")
    extra: List[str] = [f"--dslx_stdlib_path={stdlib}"]
    extra.extend(cfg.get("base_flags", []))
    for env_name in cfg.get("env_flags", []):
        v = _get_env(env_name) or ""
        extra.extend(_env_flag_builder(env_name, v))
    return extra


def _build_toolchain_toml(tool_dir: str) -> str:
    dslx_stdlib_path = os.path.join(tool_dir, "xls", "dslx", "stdlib")

    additional_dslx_paths_list = _get_env_list("XLSYNTH_DSLX_PATH", ":")
    enable_warnings_list = _get_env_list("XLSYNTH_DSLX_ENABLE_WARNINGS", ",")
    disable_warnings_list = _get_env_list("XLSYNTH_DSLX_DISABLE_WARNINGS", ",")

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
    lines.append(f'tool_path = "{tool_dir}"')
    lines.append("")
    lines.append("[toolchain.dslx]")
    lines.append(f'dslx_stdlib_path = "{dslx_stdlib_path}"')
    lines.append(f"dslx_path = {repr(additional_dslx_paths_list)}")
    lines.append(f"enable_warnings = {repr(enable_warnings_list)}")
    lines.append(f"disable_warnings = {repr(disable_warnings_list)}")
    lines.append("")
    lines.append("[toolchain.codegen]")
    lines.extend(_toml_lines_from_regular_envs(codegen_regular_envs))
    lines.extend(_toml_lines_from_bool_envs(codegen_bool_envs))

    # Use escaped newlines so the generated Python remains single-line literals.
    return "\\n".join(lines) + "\\n"


def _driver(args: argparse.Namespace) -> int:
    tools_dir = _require_env("XLSYNTH_TOOLS")
    driver_dir = _require_env("XLSYNTH_DRIVER_DIR")
    driver_path = os.path.join(driver_dir, "xlsynth-driver")
    passthrough = list(args.passthrough)
    toml = _build_toolchain_toml(tools_dir)
    with tempfile.NamedTemporaryFile("w",
                                     delete=False,
                                     prefix="xlsynth_toolchain_",
                                     suffix=".toml") as tf:
        tf.write(toml)
        toolchain_path = tf.name
    try:
        cmd = [
            driver_path, f"--toolchain={toolchain_path}", args.subcommand,
            *passthrough
        ]
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    finally:
        try:
            os.unlink(toolchain_path)
        except OSError:
            pass


def _tool(args: argparse.Namespace) -> int:
    tools_dir = _require_env("XLSYNTH_TOOLS")
    tool_path = os.path.join(tools_dir, args.tool)
    passthrough = list(args.passthrough)
    extra = _build_extra_args_for_tool(args.tool, tools_dir)
    if extra:
        passthrough = extra + passthrough

    cmd = [tool_path, *passthrough]
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="xlsynth_runner", allow_abbrev=False)
    sub = parser.add_subparsers(dest="mode")

    # No global arguments; subcommands define their own.

    p_driver = sub.add_parser("driver")
    p_driver.add_argument("subcommand")
    p_driver.set_defaults(func=_driver)

    p_tool = sub.add_parser("tool")
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
    """
