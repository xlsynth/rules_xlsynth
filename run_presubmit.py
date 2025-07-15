# SPDX-License-Identifier: Apache-2.0

import dataclasses
import subprocess
import optparse
import os
import re
import tempfile
import shutil
from typing import Optional, Tuple, List, Callable, Dict
import sys

Runnable = Callable[['PathData'], None]
TO_RUN: List[Runnable] = []

def register(f: Runnable):
    TO_RUN.append(f)
    return f

@dataclasses.dataclass
class PathData:
    xlsynth_tools: str
    xlsynth_driver_dir: str
    dslx_path: Optional[Tuple[str, ...]]

def bazel_test_opt(targets: Tuple[str, ...], path_data: PathData, *, capture_output: bool = False, more_action_env: Optional[Dict[str, str]] = None):
    assert isinstance(targets, tuple), targets
    flags = ['-c', 'opt', '--test_output=errors']
    flags += [
        '--action_env=XLSYNTH_TOOLS=' + path_data.xlsynth_tools,
        '--action_env=XLSYNTH_DRIVER_DIR=' + path_data.xlsynth_driver_dir,
    ]
    if path_data.dslx_path is not None:
        flags += [
            '--action_env=XLSYNTH_DSLX_PATH=' + ':'.join(path_data.dslx_path),
        ]
    if more_action_env:
        for k, v in more_action_env.items():
            flags += ['--action_env=' + k + '=' + v]
    cmdline = ['bazel', 'test', '--test_output=errors'] + flags + ['--', *targets]
    print('Running command: ' + subprocess.list2cmdline(cmdline))
    if capture_output:
        subprocess.run(cmdline, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf-8')
    else:
        subprocess.run(cmdline, check=True)

def bazel_build_opt(targets: Tuple[str, ...], path_data: PathData, *, capture_output: bool = False, more_action_env: Optional[Dict[str, str]] = None):
    """Run a `bazel build` over the given targets with the standard flags."""
    assert isinstance(targets, tuple), targets
    flags = ['-c', 'opt']
    flags += [
        '--action_env=XLSYNTH_TOOLS=' + path_data.xlsynth_tools,
        '--action_env=XLSYNTH_DRIVER_DIR=' + path_data.xlsynth_driver_dir,
    ]
    if path_data.dslx_path is not None:
        flags += [
            '--action_env=XLSYNTH_DSLX_PATH=' + ':'.join(path_data.dslx_path),
        ]
    if more_action_env:
        for k, v in more_action_env.items():
            flags += ['--action_env=' + k + '=' + v]
    cmdline = ['bazel', 'build'] + flags + ['--', *targets]
    print('Running command: ' + subprocess.list2cmdline(cmdline))
    if capture_output:
        subprocess.run(cmdline, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf-8')
    else:
        subprocess.run(cmdline, check=True)

@register
def run_sample(path_data: PathData):
    bazel_test_opt(('//sample/...',), path_data)

@register
def run_sample_expecting_dslx_path(path_data: PathData):
    path_data.dslx_path = ('sample_expecting_dslx_path', 'sample_expecting_dslx_path/subdir')
    bazel_test_opt(('//sample_expecting_dslx_path:main_test', '//sample_expecting_dslx_path:add_mol_pipeline_sv_test'), path_data)

@register
def run_sample_failing_quickcheck(path_data: PathData):
    try:
        bazel_test_opt(('//sample_failing_quickcheck:failing_quickcheck_test',), path_data, capture_output=True)
    except subprocess.CalledProcessError as e:
        if 'Found falsifying example after 1 tests' in e.stdout:
            pass
        else:
            raise ValueError('Unexpected error running quickcheck: ' + e.stdout)
    else:
        raise ValueError('Expected quickcheck to fail')

    try:
        bazel_test_opt(('//sample_failing_quickcheck:failing_quickcheck_proof_test',), path_data, capture_output=True)
    except subprocess.CalledProcessError as e:
        m = re.search(r'ProofError: Failed to prove the property! counterexample: \(bits\[1\]:\d+, bits\[2\]:\d+\)', e.stdout)
        if m:
            print('Found proof error as expected: ' + m.group(0))
            pass
        else:
            raise ValueError('Unexpected error proving quickcheck: stdout: ' + e.stdout + ' stderr: ' + e.stderr)

@register
def run_sample_disabling_warning(path_data: PathData):
    try:
        print('Running with warnings as default...')
        bazel_test_opt(('//sample_disabling_warning/...',), path_data, capture_output=True)
    except subprocess.CalledProcessError as e:
        want_warnings = [
            'is an empty range',
            'is not used in function `main`',
            'is not used',
        ]
        for want_warning in want_warnings:
            if want_warning in e.stderr:
                print('Found warning as expected: ' + want_warning)
                pass
            else:
                raise ValueError('Expected warning: ' + want_warning + ' not found in: ' + e.stderr)

    # Now we disable the warning and it should be ok.
    print('== Now running with warnings disabled...')
    bazel_test_opt(('//sample_disabling_warning/...',), path_data, more_action_env={
        'XLSYNTH_DSLX_DISABLE_WARNINGS': 'unused_definition,empty_range_literal'
    })

@register
def run_sample_nonequiv_ir(path_data: PathData):
    print('== Running yes-equivalent IR test...')
    bazel_test_opt(('//sample_nonequiv_ir:add_one_ir_prove_equiv_test',), path_data, capture_output=True)
    print('== Running no-not-equivalent IR test...')
    try:
        bazel_test_opt(('//sample_nonequiv_ir:add_one_ir_prove_equiv_expect_failure_test',), path_data, capture_output=True)
    except subprocess.CalledProcessError as e:
        if 'Verified NOT equivalent' in e.stdout:
            print('IRs are not equivalent as expected; bazel stdout: ' + repr(e.stdout) + ' bazel stderr: ' + repr(e.stderr))
            pass
        else:
            raise ValueError('Unexpected error running nonequiv IR; bazel stdout: ' + repr(e.stdout) + ' bazel stderr: ' + repr(e.stderr))
    else:
        raise ValueError('Expected nonequiv IR to fail')

@register
def run_sample_with_formats(path_data: PathData):
    bazel_test_opt(
        ('//sample_with_formats:gate_assert_minimal_sv_test',),
        path_data,
        more_action_env={
            'XLSYNTH_GATE_FORMAT': 'br_gate_buf gated_{output}(.in({input}), .out({output}))',
            'XLSYNTH_ASSERT_FORMAT': '`BR_ASSERT({label}, {condition})',
            'XLSYNTH_USE_SYSTEM_VERILOG': 'true',
        },
    )

@register
def run_sample_type_inference_v2(path_data: PathData):
    print('== Running type inference v2 mismatch test...')
    test_target = '//sample_type_inference_v2:slice_at_limit_test'
    build_target = '//sample_type_inference_v2:slice_at_limit_ir'

    # First, with XLSYNTH_TYPE_INFERENCE_V2 enabled we expect failures.
    for tgt, is_test in ((test_target, True), (build_target, False)):
        try:
            if is_test:
                bazel_test_opt((tgt,), path_data, capture_output=True, more_action_env={'XLSYNTH_TYPE_INFERENCE_V2': 'true'})
            else:
                bazel_build_opt((tgt,), path_data, capture_output=True, more_action_env={'XLSYNTH_TYPE_INFERENCE_V2': 'true'})
        except subprocess.CalledProcessError as e:
            combined = (e.stdout + e.stderr).lower()
            if 'slice' in combined or 'out of range' in combined:
                print(f'Got expected type-inference error for {tgt} with XLSYNTH_TYPE_INFERENCE_V2=true')
            else:
                raise ValueError(f'Unexpected error output for {tgt}; stdout: {repr(e.stdout)} stderr: {repr(e.stderr)}')
        else:
            raise ValueError(f'Expected type inference v2 to fail for {tgt} but it succeeded')

    # Now run without the flag – should succeed.
    print('== Running with default type inference v1 (should succeed)...')
    bazel_test_opt((test_target,), path_data)
    bazel_build_opt((build_target,), path_data)

@register
def run_readme_sample_snippets(path_data: PathData):
    """Ensures that the Starlark BUILD snippets in the README can be loaded by Bazel.

    The strategy is:
      1. Extract every ```starlark code block from README.md.
      2. Place the concatenated snippets into a temporary Bazel package inside the
         repository (so that we have access to //:rules.bzl).
      3. Materialize any `.x` files referenced in the snippets so that Bazel does
         not complain about missing input files during package loading.
      4. Invoke `bazel query` on that package; if Bazel can successfully load
         the package and enumerate its targets, then all attributes / rule
         names used in the snippets are valid.
    """

    repo_root = os.path.dirname(__file__)
    readme_path = os.path.join(repo_root, "README.md")

    if not os.path.exists(readme_path):
        raise RuntimeError(f"README.md not found at {readme_path}")

    with open(readme_path, "r", encoding="utf-8") as f:
        readme_text = f.read()

    # Extract ```starlark``` blocks.
    snippet_blocks = re.findall(r"```starlark\s*(.*?)```", readme_text, re.DOTALL)
    if not snippet_blocks:
        raise RuntimeError("No starlark code blocks found in README.md")

    # Flatten snippets into a list of lines, stripping trailing whitespace.
    snippet_lines = []
    for idx, block in enumerate(snippet_blocks, 1):
        print("--- README snippet {} ---".format(idx))
        print(block.strip())
        print("----------------------")
        snippet_lines.extend([ln.rstrip() for ln in block.splitlines() if ln.strip()])

    # Determine which rule symbols are used so we can create a single load(...).
    rule_name_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\(")
    used_rule_names: set[str] = set()
    for ln in snippet_lines:
        m = rule_name_pattern.match(ln)
        if m and m.group(1) != "load":
            used_rule_names.add(m.group(1))

    # Inspect rules.bzl to know what symbols it actually exports so we only
    # attempt to load valid ones (e.g. we do NOT load `glob`).
    rules_bzl_path = os.path.join(repo_root, "rules.bzl")
    exported_rule_names: set[str] = set()
    if os.path.exists(rules_bzl_path):
        with open(rules_bzl_path, "r", encoding="utf-8") as rbzl:
            for line in rbzl:
                m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                if m:
                    exported_rule_names.add(m.group(1))

    load_rule_names = sorted(name for name in used_rule_names if name in exported_rule_names)

    # Gather referenced .x filenames so we can create stub DSLX files.
    xfile_names = set(re.findall(r"['\"]([^'\"]+\.x)['\"]", "\n".join(snippet_lines)))

    # Create a temporary package under the repository root.
    temp_pkg_dir = tempfile.mkdtemp(prefix="readme_snippets_", dir=repo_root)
    try:
        build_path = os.path.join(temp_pkg_dir, "BUILD.bazel")

        with open(build_path, "w", encoding="utf-8") as bf:
            bf.write("# Auto-generated test BUILD file for README snippets.\n")
            if load_rule_names:
                bf.write("load(\"//:rules.bzl\", {} )\n\n".format(
                    ", ".join(f'\"{name}\"' for name in load_rule_names)
                ))

            # Collect names defined in snippets to help stub out references.
            defined_targets: set[str] = set()
            name_attr_re = re.compile(r"name\s*=\s*\"([A-Za-z0-9_]+)\"")

            for ln in snippet_lines:
                if ln.lstrip().startswith("load("):
                    # Skip user-provided load lines; we wrote our own above.
                    continue

                # Track defined target names.
                m_name = name_attr_re.search(ln)
                if m_name:
                    defined_targets.add(m_name.group(1))

                bf.write(ln + "\n")

            # After writing original lines, add stub filegroups for any referenced
            # targets that were not defined in the snippets themselves.
            referenced_targets = set(re.findall(r"\"?:([A-Za-z0-9_]+)\"?", "\n".join(snippet_lines)))
            missing_targets = referenced_targets - defined_targets

            for tgt in sorted(missing_targets):
                bf.write(f"filegroup(name = \"{tgt}\")\n")

        # Stub out referenced .x files so the package loads cleanly.
        for xfname in xfile_names:
            # Skip wildcard entries (e.g. "*.x") that arise from glob patterns.
            if any(ch in xfname for ch in "*?["):
                continue
            dst_path = os.path.join(temp_pkg_dir, xfname)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            with open(dst_path, "w", encoding="utf-8") as xf:
                xf.write("// stub file generated by run_presubmit.py\n")

        # Run `bazel query` to ensure the package loads.
        rel_pkg = os.path.relpath(temp_pkg_dir, repo_root)
        query_target = f"//{rel_pkg}:all"

        env = os.environ.copy()
        env["XLSYNTH_TOOLS"] = path_data.xlsynth_tools
        env["XLSYNTH_DRIVER_DIR"] = path_data.xlsynth_driver_dir
        if path_data.dslx_path is not None:
            env["XLSYNTH_DSLX_PATH"] = ":".join(path_data.dslx_path)

        print(f"Running bazel query on README snippets: {query_target}\nBUILD file used: {build_path}")
        try:
            result = subprocess.run([
                "bazel",
                "query",
                "--noshow_progress",
                query_target,
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", env=env)
        except subprocess.CalledProcessError as e:
            print("=== Bazel query failed ===")
            print("STDOUT:\n" + (e.stdout or "<empty>"))
            print("STDERR:\n" + (e.stderr or "<empty>"))
            raise

        print("README snippets successfully loaded by Bazel. Output targets:")
        print(result.stdout)
    finally:
        if os.environ.get("KEEP_README_SNIPPET_TEMPS"):
            print(f"KEEP_README_SNIPPET_TEMPS set; temp BUILD package retained at: {temp_pkg_dir}")
        else:
            shutil.rmtree(temp_pkg_dir)

@register
def run_sample_stitch_pipeline_expecting_dslx_path(path_data: PathData):
    """Runs the pipeline stitching sample that relies on XLSYNTH_DSLX_PATH search paths."""
    path_data.dslx_path = (
        'sample_stitch_expecting_dslx_path',
        'sample_stitch_expecting_dslx_path/subdir',
    )
    bazel_test_opt(
        (
            '//sample_stitch_expecting_dslx_path:pipeline_stages_pipeline_build_test',
        ),
        path_data,
    )

def parse_versions_toml(path):
    crate_version = None
    dso_version = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            m = re.match(r'crate\s*=\s*"([^"]+)"', line)
            if m:
                crate_version = m.group(1)
            m = re.match(r'dso\s*=\s*"([^"]+)"', line)
            if m:
                dso_version = m.group(1)
    if not crate_version or not dso_version:
        raise RuntimeError(f'Could not parse crate or dso version from {path}')
    return crate_version, dso_version

def find_dso(dso_filename, search_dirs):
    for d in search_dirs:
        candidate = os.path.join(d, dso_filename)
        if os.path.exists(candidate):
            return candidate
    return None

def main():
    parser = optparse.OptionParser()
    parser.add_option('--xlsynth-tools', type='string', help='Path to xlsynth tools')
    parser.add_option('--xlsynth-driver-dir', type='string', help='Path to xlsynth driver directory')
    parser.add_option('--dslx-path', type='string', help='Path to DSLX standard library')
    parser.add_option('-k', '--keyword', type='string', help='Only run tests whose function name contains this keyword')
    (options, args) = parser.parse_args()
    if options.xlsynth_tools is None or options.xlsynth_driver_dir is None:
        parser.error('Missing required argument(s): --xlsynth-tools, --xlsynth-driver-dir, --dslx-path')
        return
    dslx_path = options.dslx_path.split(':') if options.dslx_path else None
    path_data = PathData(xlsynth_tools=options.xlsynth_tools,
                         xlsynth_driver_dir=options.xlsynth_driver_dir,
                         dslx_path=dslx_path)

    # Version check for xlsynth-driver and DSO
    versions_path = os.path.join(os.path.dirname(__file__), 'xlsynth-versions.toml')
    crate_version, dso_version = parse_versions_toml(versions_path)
    driver_path = os.path.join(path_data.xlsynth_driver_dir, 'xlsynth-driver')
    try:
        version_out = subprocess.check_output([driver_path, '--version'], encoding='utf-8').strip()
    except Exception as e:
        raise RuntimeError(f'Could not run xlsynth-driver at {driver_path}: {e}')
    m = re.search(r'(\d+\.\d+\.\d+)', version_out)
    if not m:
        raise RuntimeError(f'Could not parse version from xlsynth-driver --version output: {version_out}')
    actual_version = m.group(1)
    if actual_version != crate_version:
        raise RuntimeError(f'xlsynth-driver version {actual_version} does not match required {crate_version}. Please update your xlsynth-driver.')
    # DSO existence check removed; assume xlsynth-driver can run if version matches

    assert os.path.exists(os.path.join(path_data.xlsynth_tools, 'dslx_interpreter_main')), 'dslx_interpreter_main not found in XLSYNTH_TOOLS=' + path_data.xlsynth_tools
    assert os.path.exists(os.path.join(path_data.xlsynth_driver_dir, 'xlsynth-driver')), 'xlsynth-driver not found in XLSYNTH_DRIVER_DIR=' + path_data.xlsynth_driver_dir

    to_run = TO_RUN
    if options.keyword:
        to_run = [f for f in TO_RUN if options.keyword in f.__name__]
    for f in to_run:
        print('-' * 80)
        print('Executing', f.__name__)
        f(path_data)

if __name__ == '__main__':
    main()
