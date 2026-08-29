# SPDX-License-Identifier: Apache-2.0

import ast
import pathlib
import subprocess
import sys
import tempfile
import unittest


class MakeEnvHelpersTest(unittest.TestCase):

    def test_embedded_source_roundtrips_quotes_and_backslashes(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parent
        fixture = 'def fixture():\n    """An embedded docstring."""\n    return "line\\n\\\\path"\n'
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "runner.py"
            source.write_text(fixture)
            result = subprocess.run(
                [sys.executable, str(repo_root / "make_env_helpers.py"), "--source", str(source), "--stdout"],
                check = True,
                stdout = subprocess.PIPE,
                universal_newlines = True,
            )
        # The generated Starlark function uses only Python-compatible string syntax.
        function = ast.parse(result.stdout).body[0]
        embedded = ast.literal_eval(function.body[-1].value)
        self.assertEqual(embedded, fixture + "    ")
        ast.parse(embedded)

    def test_generated_env_helpers_matches_checked_in_file(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parent
        generator = repo_root / "make_env_helpers.py"
        env_helpers_bzl = repo_root / "env_helpers.bzl"
        env_helpers_py = repo_root / "env_helpers.py"

        with tempfile.TemporaryDirectory() as tmp:
            output_path = pathlib.Path(tmp) / "env_helpers.bzl"
            subprocess.run(
                [
                    sys.executable,
                    str(generator),
                    "--output",
                    str(output_path),
                    "--source",
                    str(env_helpers_py),
                ],
                check=True,
            )

            generated = output_path.read_text()
            expected = env_helpers_bzl.read_text()

            self.assertEqual(
                generated,
                expected,
                "env_helpers.bzl is out of date; run `python make_env_helpers.py`",
            )


if __name__ == "__main__":
    unittest.main()
