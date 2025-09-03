#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import argparse
import sys
import textwrap
from pathlib import Path

_DOCSTRING = """Returns the embedded xlsynth_runner.py source.

The returned program reads XLSYNTH_* from the action execution environment
and invokes either the driver (via the 'driver' subcommand) or a tool
(via the 'tool' subcommand), forwarding passthrough flags accordingly.
"""


def _generate_bzl(py_source: str) -> str:
    header_lines = [
        "def python_runner_source():",
    ]
    docstring = textwrap.indent(textwrap.dedent(f'"""{_DOCSTRING}\n"""'),
                                "    ").rstrip()
    escaped_python = py_source.replace('"""', '\"\"\"')
    python_lines = escaped_python.splitlines()
    if python_lines:
        return_lines = [f'    return """{python_lines[0]}']
        return_lines.extend(python_lines[1:])
    else:
        return_lines = ['    return """']
    return_lines.append('    """')
    return "\n".join([*header_lines, docstring, *return_lines, ""])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Regenerate env_helpers.bzl")
    parser.add_argument("--output", type=Path, default=Path("env_helpers.bzl"))
    parser.add_argument("--source", type=Path, default=Path("env_helpers.py"))
    parser.add_argument("--stdout",
                        action="store_true",
                        help="Write to stdout instead of a file")
    args = parser.parse_args(argv[1:])

    py_source = args.source.read_text()
    generated = _generate_bzl(py_source)

    if args.stdout:
        sys.stdout.write(generated)
    else:
        args.output.write_text(generated)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
