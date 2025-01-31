import dataclasses
import subprocess
import optparse
import os
from typing import Optional, Tuple, List, Callable

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

def bazel_test_opt(targets: Tuple[str, ...], path_data: PathData, capture_output: bool = False):
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
    cmdline_args = ['bazel', 'test', '--test_output=errors'] + flags + ['--', *targets]
    cmdline = subprocess.list2cmdline(cmdline_args)
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
        bazel_test_opt(('//sample_failing_quickcheck/...',), path_data, capture_output=True)
    except subprocess.CalledProcessError as e:
        if 'Found falsifying example after 1 tests' in e.stdout:
            return
        else:
            raise ValueError('Unexpected error running quickcheck: ' + e.stdout)
    else:
        raise ValueError('Expected quickcheck to fail')

def main():
    parser = optparse.OptionParser()
    parser.add_option('--xlsynth-tools', type='string', help='Path to xlsynth tools')
    parser.add_option('--xlsynth-driver-dir', type='string', help='Path to xlsynth driver directory')
    parser.add_option('--dslx-path', type='string', help='Path to DSLX standard library')
    (options, args) = parser.parse_args()
    if options.xlsynth_tools is None or options.xlsynth_driver_dir is None:
        parser.error('Missing required argument(s): --xlsynth-tools, --xlsynth-driver-dir, --dslx-path')
        return
    dslx_path = options.dslx_path.split(':') if options.dslx_path else None
    path_data = PathData(xlsynth_tools=options.xlsynth_tools,
                         xlsynth_driver_dir=options.xlsynth_driver_dir,
                         dslx_path=dslx_path)
    
    assert os.path.exists(os.path.join(path_data.xlsynth_tools, 'dslx_interpreter_main')), 'dslx_interpreter_main not found in XLSYNTH_TOOLS=' + path_data.xlsynth_tools
    assert os.path.exists(os.path.join(path_data.xlsynth_driver_dir, 'xlsynth-driver')), 'xlsynth-driver not found in XLSYNTH_DRIVER_DIR=' + path_data.xlsynth_driver_dir

    for f in TO_RUN:
        print('Executing', f.__name__)
        f(path_data)

if __name__ == '__main__':
    main()
