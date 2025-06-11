# SPDX-License-Identifier: Apache-2.0

import dataclasses
import subprocess
import optparse
import os
import re
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
