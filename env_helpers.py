#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from enum import Enum
from typing import Any, Dict, List, NamedTuple, Optional


_TOOL_CONFIG = {
    "dslx_interpreter_main": {
        "base_flags": ["--compare=jit", "--alsologtostderr"],
        "dslx_config": True,
        "dslx_scalar_settings": [],
        "needs_dslx_stdlib_flag": True,
    },
    "prove_quickcheck_main": {
        "base_flags": ["--alsologtostderr"],
        "dslx_config": True,
        "dslx_scalar_settings": [],
        "needs_dslx_stdlib_flag": True,
    },
    "typecheck_main": {
        "base_flags": [],
        "dslx_config": True,
        "dslx_scalar_settings": [],
        "needs_dslx_stdlib_flag": True,
    },
    "dslx_fmt": {
        "base_flags": [],
        "dslx_config": False,
        "dslx_scalar_settings": [],
        "needs_dslx_stdlib_flag": False,
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


def _toolchain_tool_path(toolchain_data: Dict[str, Any]) -> str:
    toolchain_section = toolchain_data.get("toolchain", {})
    tool_path = toolchain_section.get("tool_path", "")
    return _resolve_runtime_path(tool_path)


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


def _runtime_library_env_var(sys_platform: str) -> str:
    if sys_platform == "darwin":
        return "DYLD_LIBRARY_PATH"
    return "LD_LIBRARY_PATH"


def _build_extra_args_for_tool(tool: str, toolchain_data: Dict[str, Any]) -> List[str]:
    cfg = _TOOL_CONFIG.get(tool)
    if not cfg:
        return []
    dslx_cfg = _toolchain_dslx_config(toolchain_data)
    extra: List[str] = []
    if cfg.get("needs_dslx_stdlib_flag", True):
        stdlib = _resolve_runtime_path(dslx_cfg.get("dslx_stdlib_path", ""))
        if not stdlib:
            raise RuntimeError("Toolchain TOML is missing toolchain.dslx.dslx_stdlib_path")
        extra.append(f"--dslx_stdlib_path={stdlib}")
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
        extra_env: Optional[Dict[str, str]] = None,
        runtime_library_path: str,
        stdout_path: str,
        sys_platform: str = sys.platform) -> int:
    env = os.environ.copy()
    resolved_runtime_library_path = _resolve_runtime_path(runtime_library_path)
    if resolved_runtime_library_path:
        runtime_env_var = _runtime_library_env_var(sys_platform)
        existing = env.get(runtime_env_var, "")
        env[runtime_env_var] = (
            resolved_runtime_library_path
            if not existing
            else resolved_runtime_library_path + os.pathsep + existing
        )
    if extra_env is not None:
        for key, value in extra_env.items():
            if value:
                env[key] = value
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
    toolchain_data = _parse_toolchain_toml(args.toolchain)
    extra_env = {}
    tool_path = _toolchain_tool_path(toolchain_data)
    if tool_path:
        # Older driver releases still discover external prover tools through
        # XLSYNTH_TOOLS even when --toolchain is provided.
        extra_env["XLSYNTH_TOOLS"] = tool_path
    cmd = [
        _resolve_executable_path(args.driver_path),
        f"--toolchain={args.toolchain}",
        args.subcommand,
        *list(args.passthrough),
    ]
    return _run_subprocess(
        cmd,
        extra_env = extra_env,
        runtime_library_path = args.runtime_library_path,
        stdout_path = args.stdout_path,
    )


def _quickcheck(args: argparse.Namespace) -> int:
    """Run Bitwuzla QuickCheck proofs and preserve per-property Bazel reporting."""
    dslx_config = _toolchain_dslx_config(_parse_toolchain_toml(args.toolchain))
    passthrough = [
        "--dslx_input_file", args.dslx_input_file,
        "--solver", "bitwuzla",
        "--assertion-semantics", "never",
    ]
    stdlib = _resolve_runtime_path(dslx_config.get("dslx_stdlib_path", ""))
    if stdlib:
        passthrough.extend(["--dslx_stdlib_path", stdlib])
    import_paths = dslx_config.get("dslx_path", [])
    if import_paths:
        passthrough.extend(["--dslx_path", ";".join(import_paths)])
    if args.top:
        # The driver uses substring matching; the Bazel rule promises a full match.
        passthrough.extend(["--test_filter", "^(?:" + args.top + ")$"])

    with tempfile.TemporaryDirectory(prefix = "xlsynth_quickcheck_") as temp_dir:
        report_path = os.path.join(temp_dir, "result.json")
        driver_args = argparse.Namespace(
            driver_path = args.driver_path,
            runtime_library_path = args.runtime_library_path,
            stdout_path = "",
            toolchain = args.toolchain,
            subcommand = "prove-quickcheck",
            passthrough = passthrough + ["--output_json", report_path] + list(args.passthrough),
        )
        tests: List[Dict[str, Any]] = []
        error = ""
        try:
            # The driver's proof API does not apply configured warning settings.
            # Check them using the same selected toolchain before invoking it.
            typecheck_args = argparse.Namespace(
                runtime_library_path = args.runtime_library_path,
                stdout_path = "",
                toolchain = args.toolchain,
                tool = "typecheck_main",
                passthrough = [args.dslx_input_file, "--output_path=" + os.devnull],
            )
            typecheck_returncode = _tool(typecheck_args)
            if typecheck_returncode:
                raise ValueError("DSLX typechecking failed (exit code {})".format(typecheck_returncode))
            returncode = _driver(driver_args)
            tests = _read_quickcheck_results(report_path)
            if returncode and all(test["success"] for test in tests):
                raise ValueError("xlsynth-driver failed despite a successful proof report")
        except (OSError, ValueError) as exc:
            error = "QuickCheck proof runner failed: " + str(exc)
            print(error, file = sys.stderr)
            returncode = 1
        xml_path = os.environ.get("XML_OUTPUT_FILE", "")
        if xml_path:
            _write_quickcheck_xml(xml_path, args.dslx_input_file, tests, error)
        return returncode or (0 if all(test["success"] for test in tests) else 1)


def _read_quickcheck_results(report_path: str) -> List[Dict[str, Any]]:
    """Reject missing, malformed, empty, or inconsistent proof reports."""
    with open(report_path, "r", encoding = "utf-8") as report_file:
        result = json.load(report_file)
    if not isinstance(result, dict) or type(result.get("success")) is not bool:
        raise ValueError("Missing Boolean proof status")
    tests = result.get("tests")
    if tests == []:
        raise ValueError("No matching quickcheck functions found")
    if not isinstance(tests, list):
        raise ValueError("Missing QuickCheck results")
    names = set()
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("name"), str) or not test["name"]:
            raise ValueError("Missing QuickCheck property name")
        if test["name"] in names:
            raise ValueError("Duplicate QuickCheck property name: " + test["name"])
        names.add(test["name"])
        if type(test.get("success")) is not bool:
            raise ValueError("Missing Boolean property status")
        if type(test.get("time_micros")) is not int or test["time_micros"] < 0:
            raise ValueError("Invalid QuickCheck duration")
        if test.get("counterexample") is not None and not isinstance(test["counterexample"], str):
            raise ValueError("Invalid QuickCheck diagnostic")
    if result["success"] != all(test["success"] for test in tests):
        raise ValueError("Inconsistent QuickCheck proof status")
    return tests


def _write_quickcheck_xml(path: str, source: str, tests: List[Dict[str, Any]], error: str) -> None:
    """Translate driver results to JUnit without reporting infrastructure errors as proofs."""
    suite_name = os.path.splitext(os.path.basename(source))[0]
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root, "testsuite",
        name = suite_name,
        tests = str(len(tests) + bool(error)),
        failures = str(sum(not test["success"] for test in tests)),
        errors = str(int(bool(error))),
        time = "{:.6f}".format(sum(test["time_micros"] for test in tests) / 1e6),
    )
    for test in tests:
        case = ET.SubElement(
            suite, "testcase",
            name = test["name"], classname = suite_name, file = source,
            time = "{:.6f}".format(test["time_micros"] / 1e6),
        )
        if not test["success"]:
            failure = ET.SubElement(case, "failure", message = "QuickCheck proof did not succeed")
            failure.text = test.get("counterexample") or "No counterexample was reported"
    if error:
        case = ET.SubElement(suite, "testcase", name = "proof_runner", classname = suite_name, file = source)
        ET.SubElement(case, "error", message = error).text = error
    ET.ElementTree(root).write(path, encoding = "utf-8", xml_declaration = True)


def _tool(args: argparse.Namespace) -> int:
    toolchain_data = _parse_toolchain_toml(args.toolchain)
    tool_path_root = _toolchain_tool_path(toolchain_data)
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

    p_quickcheck = sub.add_parser("quickcheck", allow_abbrev=False)
    p_quickcheck.add_argument("--driver_path", required=True)
    p_quickcheck.add_argument("--runtime_library_path", default="")
    p_quickcheck.add_argument("--toolchain", required=True)
    p_quickcheck.add_argument("--dslx_input_file", required=True)
    p_quickcheck.add_argument("--top", default="")
    p_quickcheck.set_defaults(func=_quickcheck)

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
