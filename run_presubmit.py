# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Optional, Tuple, List, Callable, Dict, Set
import subprocess
import optparse
import os
from pathlib import Path
import re
import tempfile
import shutil
import sys

import materialize_xls_bundle

Runnable = Callable[['PresubmitConfig'], None]
TO_RUN: List[Runnable] = []

def register(f: Runnable):
    TO_RUN.append(f)
    return f


@dataclass(frozen = True)
class PresubmitConfig:
    repo_root: Path
    dslx_path: Optional[Tuple[str, ...]]
    xlsynth_driver_version: str
    xls_version: str


def _build_setting_override_flags(more_action_env: Optional[Dict[str, str]]) -> List[str]:
    if not more_action_env:
        return []
    mapping = {
        'XLSYNTH_DSLX_PATH': '@rules_xlsynth//config:dslx_path',
        'XLSYNTH_DSLX_ENABLE_WARNINGS': '@rules_xlsynth//config:enable_warnings',
        'XLSYNTH_DSLX_DISABLE_WARNINGS': '@rules_xlsynth//config:disable_warnings',
        'XLSYNTH_TYPE_INFERENCE_V2': '@rules_xlsynth//config:type_inference_v2',
        'XLSYNTH_GATE_FORMAT': '@rules_xlsynth//config:gate_format',
        'XLSYNTH_ASSERT_FORMAT': '@rules_xlsynth//config:assert_format',
        'XLSYNTH_USE_SYSTEM_VERILOG': '@rules_xlsynth//config:use_system_verilog',
        'XLSYNTH_ADD_INVARIANT_ASSERTIONS': '@rules_xlsynth//config:add_invariant_assertions',
    }
    flags: List[str] = []
    for key, value in more_action_env.items():
        if key not in mapping:
            raise ValueError('Unsupported override key: {}'.format(key))
        flags.append('--{}={}'.format(mapping[key], value))
    return flags


def _dslx_path_flags(dslx_path: Optional[Tuple[str, ...]]) -> List[str]:
    if dslx_path is None:
        return []
    return ['--@rules_xlsynth//config:dslx_path=' + ':'.join(dslx_path)]


def _presubmit_bazel_flags(
        config: PresubmitConfig,
        *,
        dslx_path: Optional[Tuple[str, ...]] = None,
        more_action_env: Optional[Dict[str, str]] = None) -> List[str]:
    resolved_dslx_path = config.dslx_path if dslx_path is None else dslx_path
    flags = _dslx_path_flags(resolved_dslx_path)
    flags.extend(_build_setting_override_flags(more_action_env))
    return flags


def _run_bazel(
        workspace_dir: Path,
        subcommand: str,
        targets: Tuple[str, ...],
        flags: List[str],
        *,
        capture_output: bool) -> subprocess.CompletedProcess[str]:
    cmdline = [
        'bazel',
        '--bazelrc=/dev/null',
        subcommand,
        '--subcommands',
    ] + flags + ['--', *targets]
    print('Running command: ' + subprocess.list2cmdline(cmdline))
    return subprocess.run(
        cmdline,
        check = True,
        cwd = str(workspace_dir),
        stderr = subprocess.PIPE if capture_output else None,
        stdout = subprocess.PIPE if capture_output else None,
        encoding = 'utf-8' if capture_output else None,
    )


def bazel_test_opt(
        targets: Tuple[str, ...],
        config: PresubmitConfig,
        *,
        workspace_dir: Optional[Path] = None,
        capture_output: bool = False,
        dslx_path: Optional[Tuple[str, ...]] = None,
        more_action_env: Optional[Dict[str, str]] = None):
    assert isinstance(targets, tuple), targets
    flags = []
    # Force Bazel to rebuild rather than reusing the local shared disk cache so that
    # stale outputs (e.g. generated Verilog) cannot mask real regressions.
    #   * --disk_cache=  : overrides any ~/.bazelrc --disk_cache setting with an empty value
    #   * --nocache_test_results : still avoid caching test results inside the build tree
    flags += ['--nocache_test_results', '--disk_cache=', '-c', 'opt', '--test_output=errors']
    flags += _presubmit_bazel_flags(
        config,
        dslx_path = dslx_path,
        more_action_env = more_action_env,
    )
    resolved_workspace_dir = config.repo_root if workspace_dir is None else workspace_dir
    _run_bazel(resolved_workspace_dir, 'test', targets, flags, capture_output = capture_output)


def bazel_build_opt(
        targets: Tuple[str, ...],
        config: PresubmitConfig,
        *,
        workspace_dir: Optional[Path] = None,
        capture_output: bool = False,
        dslx_path: Optional[Tuple[str, ...]] = None,
        more_action_env: Optional[Dict[str, str]] = None):
    """Run a `bazel build` over the given targets with the standard flags."""
    assert isinstance(targets, tuple), targets
    flags = []
    # Disable the shared disk cache for builds as well so we always rebuild fresh.
    flags += ['--disk_cache=', '-c', 'opt']
    flags += _presubmit_bazel_flags(
        config,
        dslx_path = dslx_path,
        more_action_env = more_action_env,
    )
    resolved_workspace_dir = config.repo_root if workspace_dir is None else workspace_dir
    _run_bazel(resolved_workspace_dir, 'build', targets, flags, capture_output = capture_output)

@register
def run_sample(config: PresubmitConfig):
    bazel_test_opt(('//sample/...',), config)


@register
def run_sample_expecting_dslx_path(config: PresubmitConfig):
    bazel_test_opt(
        ('//sample_expecting_dslx_path:main_test', '//sample_expecting_dslx_path:add_mol_pipeline_sv_test'),
        config,
        dslx_path = ('sample_expecting_dslx_path', 'sample_expecting_dslx_path/subdir'),
    )


@register
def run_sample_failing_quickcheck(config: PresubmitConfig):
    try:
        bazel_test_opt(('//sample_failing_quickcheck:failing_quickcheck_test',), config, capture_output = True)
    except subprocess.CalledProcessError as e:
        if 'Found falsifying example after 1 tests' in e.stdout:
            pass
        else:
            raise ValueError('Unexpected error running quickcheck: ' + e.stdout)
    else:
        raise ValueError('Expected quickcheck to fail')

    try:
        bazel_test_opt(('//sample_failing_quickcheck:failing_quickcheck_proof_test',), config, capture_output = True)
    except subprocess.CalledProcessError as e:
        m = re.search(
            r'ProofError: Failed to prove the property! counterexample: bits\[1\]:\d+, bits\[2\]:\d+',
            e.stdout,
        )
        if m:
            print('Found proof error as expected: ' + m.group(0))
            pass
        else:
            raise ValueError('Unexpected error proving quickcheck: stdout: ' + e.stdout + ' stderr: ' + e.stderr)

@register
def run_sample_disabling_warning(config: PresubmitConfig):
    try:
        print('Running with warnings as default...')
        bazel_test_opt(('//sample_disabling_warning/...',), config, capture_output = True)
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
    bazel_test_opt(
        ('//sample_disabling_warning/...',),
        config,
        more_action_env = {
            'XLSYNTH_DSLX_DISABLE_WARNINGS': 'unused_definition,empty_range_literal',
        },
    )


@register
def run_sample_nonequiv_ir(config: PresubmitConfig):
    print('== Running yes-equivalent IR test...')
    bazel_test_opt(('//sample_nonequiv_ir:add_one_ir_prove_equiv_test',), config, capture_output = True)
    print('== Running no-not-equivalent IR test...')
    try:
        bazel_test_opt(('//sample_nonequiv_ir:add_one_ir_prove_equiv_expect_failure_test',), config, capture_output = True)
    except subprocess.CalledProcessError as e:
        if 'Verified NOT equivalent' in e.stdout:
            print('IRs are not equivalent as expected; bazel stdout: ' + repr(e.stdout) + ' bazel stderr: ' + repr(e.stderr))
            pass
        else:
            raise ValueError('Unexpected error running nonequiv IR; bazel stdout: ' + repr(e.stdout) + ' bazel stderr: ' + repr(e.stderr))
    else:
        raise ValueError('Expected nonequiv IR to fail')


@register
def run_sample_with_formats(config: PresubmitConfig):
    bazel_test_opt(
        ('//sample_with_formats:gate_assert_minimal_sv_test',),
        config,
        more_action_env = {
            'XLSYNTH_GATE_FORMAT': 'br_gate_buf gated_{output}(.in({input}), .out({output}))',
            'XLSYNTH_ASSERT_FORMAT': '`BR_ASSERT({label}, {condition})',
            'XLSYNTH_USE_SYSTEM_VERILOG': 'true',
        },
    )


@register
def run_readme_sample_snippets(config: PresubmitConfig):
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

    repo_root = config.repo_root
    readme_path = repo_root / 'README.md'

    if not readme_path.exists():
        raise RuntimeError(f"README.md not found at {readme_path}")

    with open(readme_path, "r", encoding = "utf-8") as f:
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
    used_rule_names: Set[str] = set()
    for ln in snippet_lines:
        m = rule_name_pattern.match(ln)
        if m and m.group(1) != "load":
            used_rule_names.add(m.group(1))

    # Inspect rules.bzl to know what symbols it actually exports so we only
    # attempt to load valid ones (e.g. we do NOT load `glob`).
    rules_bzl_path = repo_root / 'rules.bzl'
    exported_rule_names: Set[str] = set()
    if rules_bzl_path.exists():
        with open(rules_bzl_path, "r", encoding = "utf-8") as rbzl:
            for line in rbzl:
                m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                if m:
                    exported_rule_names.add(m.group(1))

    load_rule_names = sorted(name for name in used_rule_names if name in exported_rule_names)

    # Gather referenced .x filenames so we can create stub DSLX files.
    xfile_names = set(re.findall(r"['\"]([^'\"]+\.x)['\"]", "\n".join(snippet_lines)))

    # Create a temporary package under the repository root.
    temp_pkg_dir = tempfile.mkdtemp(prefix = 'readme_snippets_', dir = str(repo_root))
    try:
        build_path = os.path.join(temp_pkg_dir, 'BUILD.bazel')

        with open(build_path, "w", encoding="utf-8") as bf:
            bf.write("# Auto-generated test BUILD file for README snippets.\n")
            if load_rule_names:
                bf.write("load(\"//:rules.bzl\", {} )\n\n".format(
                    ", ".join(f'\"{name}\"' for name in load_rule_names)
                ))

            # Collect names defined in snippets to help stub out references.
            defined_targets: Set[str] = set()
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

        print(f"Running bazel query on README snippets: {query_target}\nBUILD file used: {build_path}")
        try:
            result = subprocess.run([
                'bazel',
                'query',
                *_presubmit_bazel_flags(config),
                '--noshow_progress',
                query_target,
            ], check = True, cwd = str(repo_root), stdout = subprocess.PIPE, stderr = subprocess.PIPE, encoding = 'utf-8')
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
def run_workspace_toolchain_smoke_example(config: PresubmitConfig):
    bazel_build_opt(
        ('//:smoke_sv_types', '//:smoke_pipeline'),
        config,
        workspace_dir = config.repo_root / 'examples' / 'workspace_toolchain_smoke',
    )


def _resolve_example_artifacts(config: PresubmitConfig, temp_root: Path) -> Dict[str, Path]:
    plan = materialize_xls_bundle.resolve_artifact_plan(
        artifact_source = 'auto',
        xls_version = config.xls_version,
        driver_version = config.xlsynth_driver_version,
    )
    if plan['mode'] == 'download':
        resolved = materialize_xls_bundle.download_versioned_artifacts(temp_root, plan['xls_version'])
        driver_path = materialize_xls_bundle.install_driver(
            temp_root,
            plan['driver_version'],
            resolved['libxls'],
            resolved['dslx_stdlib_root'],
        )
        return {
            'tools_root': resolved['tools_root'],
            'dslx_stdlib_root': resolved['dslx_stdlib_root'],
            'driver': driver_path,
            'libxls': resolved['libxls'],
        }
    return {
        'tools_root': plan['tools_root'],
        'dslx_stdlib_root': plan['dslx_stdlib_root'],
        'driver': plan['driver'],
        'libxls': plan['libxls'],
    }


def _stage_local_dev_example_tree(config: PresubmitConfig) -> Path:
    stage_root = Path('/tmp/xls-local-dev')
    with tempfile.TemporaryDirectory(prefix = 'xls_local_dev_stage_', dir = str(config.repo_root)) as temp_dir:
        temp_root = Path(temp_dir)
        resolved = _resolve_example_artifacts(config, temp_root)
        materialize_xls_bundle.ensure_clean_path(stage_root)
        stage_root.mkdir(parents = True, exist_ok = True)
        (stage_root / 'bin').mkdir(parents = True, exist_ok = True)
        (stage_root / 'xls' / 'dslx').mkdir(parents = True, exist_ok = True)
        materialize_xls_bundle.symlink_or_copy(resolved['driver'], stage_root / 'bin' / 'xlsynth-driver')
        materialize_xls_bundle.symlink_or_copy(resolved['tools_root'], stage_root / 'tools')
        materialize_xls_bundle.symlink_or_copy(
            resolved['dslx_stdlib_root'],
            stage_root / 'xls' / 'dslx' / 'stdlib',
        )
        materialize_xls_bundle.symlink_or_copy(
            resolved['libxls'],
            stage_root / materialize_xls_bundle.normalized_libxls_name(resolved['libxls']),
        )
    return stage_root


@register
def run_workspace_toolchain_local_dev_example(config: PresubmitConfig):
    if sys.platform != 'linux':
        print('Skipping local_paths example on non-Linux hosts; MODULE.bazel is pinned to libxls.so')
        return
    staged_root = _stage_local_dev_example_tree(config)
    print('Staged local_paths example inputs at {}'.format(staged_root))
    bazel_build_opt(
        ('//:smoke_sv_types', '//:smoke_pipeline'),
        config,
        workspace_dir = config.repo_root / 'examples' / 'workspace_toolchain_local_dev',
    )


@register
def run_sample_stitch_pipeline_expecting_dslx_path(config: PresubmitConfig):
    """Runs the pipeline stitching sample that relies on the configured DSLX import paths."""
    bazel_test_opt(
        (
            '//sample_stitch_expecting_dslx_path:pipeline_stages_pipeline_build_test',
        ),
        config,
        dslx_path = (
            'sample_stitch_expecting_dslx_path',
            'sample_stitch_expecting_dslx_path/subdir',
        ),
    )


@register
def run_sample_invariant_assertions(config: PresubmitConfig):
    """Builds a tiny design twice – with and without invariant assertions –
    and checks that the flag actually toggles assertion emission in the
    generated SystemVerilog.
    """
    target = "//sample_invariant_assertions:array_match_sv"
    repo_root = str(config.repo_root)

    # First, build with the flag *disabled* (explicit "false") and record the
    # produced Verilog so we know what the baseline looks like.
    bazel_build_opt((target,), config, more_action_env = {"XLSYNTH_ADD_INVARIANT_ASSERTIONS": "false"})
    sv_path = os.path.join(repo_root, "bazel-bin", "sample_invariant_assertions", "array_match_sv.sv")
    with open(sv_path, "r", encoding="utf-8") as f:
        sv_without = f.read()

    # Now, build again but with the flag enabled.
    bazel_build_opt((target,), config, more_action_env = {"XLSYNTH_ADD_INVARIANT_ASSERTIONS": "true"})
    with open(sv_path, "r", encoding="utf-8") as f:
        sv_with = f.read()

    # Heuristic: when the flag is on we expect extra assertion logic to be
    # generated. We conservatively look for the token "assert" (case-insensitive)
    # appearing more frequently when the flag is enabled.
    def count_asserts(text: str) -> int:
        return text.lower().count("assert")

    count_without = count_asserts(sv_without)
    count_with_env = count_asserts(sv_with)
    if count_with_env <= count_without:
        raise ValueError(
            "Expected more assertion machinery when enabling the build setting; got {} vs {}".format(count_with_env, count_without)
        )
    print(f"Build-setting toggling works: {count_without} -> {count_with_env} assertions.")

    # -- Now verify rule-level override behaviour.
    tgt_attr_false = "//sample_invariant_assertions:array_match_sv_attr_false"
    bazel_build_opt((tgt_attr_false,), config, more_action_env = {"XLSYNTH_ADD_INVARIANT_ASSERTIONS": "true"})
    sv_path_attr_false = os.path.join(repo_root, "bazel-bin", "sample_invariant_assertions", "array_match_sv_attr_false.sv")
    with open(sv_path_attr_false, "r", encoding="utf-8") as f:
        sv_attr_false = f.read()

    count_attr_false = count_asserts(sv_attr_false)
    if count_attr_false != count_without:
        raise ValueError(
            "Rule attribute 'false' did not override build-setting 'true'; expected {} asserts but saw {}".format(count_without, count_attr_false)
        )
    print("Rule override to 'false' correctly suppressed extra assertions despite build-setting=true.")

    tgt_attr_true = "//sample_invariant_assertions:array_match_sv_attr_true"
    bazel_build_opt((tgt_attr_true,), config, more_action_env = {"XLSYNTH_ADD_INVARIANT_ASSERTIONS": "false"})
    sv_path_attr_true = os.path.join(repo_root, "bazel-bin", "sample_invariant_assertions", "array_match_sv_attr_true.sv")
    with open(sv_path_attr_true, "r", encoding="utf-8") as f:
        sv_attr_true = f.read()

    count_attr_true = count_asserts(sv_attr_true)
    if count_attr_true <= count_without:
        raise ValueError(
            "Rule attribute 'true' did not override build-setting 'false'; counts {} vs baseline {}".format(count_attr_true, count_without)
        )
    print("Rule override to 'true' correctly enabled assertions despite build-setting=false.")

# -----------------------------------------------------------------------------

@register
def run_stitch_invariant_assertions(config: PresubmitConfig):
    """Analogous checks for dslx_stitch_pipeline rule overrides."""

    repo_root = str(config.repo_root)
    base_tgt = "//sample_stitch_invariant_assertions:stages_pipeline"

    # Build with the build setting off, record baseline.
    bazel_build_opt((base_tgt,), config, more_action_env = {"XLSYNTH_ADD_INVARIANT_ASSERTIONS": "false"})
    sv_base = os.path.join(repo_root, "bazel-bin", "sample_stitch_invariant_assertions", "stages_pipeline.sv")
    with open(sv_base, "r", encoding="utf-8") as f:
        sv_without = f.read()

    # Build with the build setting on, capture.
    bazel_build_opt((base_tgt,), config, more_action_env = {"XLSYNTH_ADD_INVARIANT_ASSERTIONS": "true"})
    with open(sv_base, "r", encoding="utf-8") as f:
        sv_with_env = f.read()

    def cnt(txt: str) -> int:
        return txt.lower().count("assert")

    base_cnt = cnt(sv_without)
    env_cnt = cnt(sv_with_env)

    if base_cnt != 0:
        raise ValueError(f"Expected zero assertions with build-setting=false; got {base_cnt}")

    if env_cnt == 0:
        raise ValueError("Expected assertions to be present with build-setting=true but count was zero")

    print(f"Stitch pipeline assertion counts: disabled={base_cnt}, enabled={env_cnt} (ok)")


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


def build_presubmit_config(repo_root: Path, dslx_path: Optional[Tuple[str, ...]]) -> PresubmitConfig:
    versions_path = repo_root / 'xlsynth-versions.toml'
    xlsynth_driver_version, xls_version = parse_versions_toml(versions_path)
    return PresubmitConfig(
        repo_root = repo_root,
        dslx_path = dslx_path,
        xlsynth_driver_version = xlsynth_driver_version,
        xls_version = xls_version,
    )


def main():
    parser = optparse.OptionParser()
    parser.add_option('--dslx-path', type = 'string', help = 'Colon-separated extra DSLX import roots for steps that need them')
    parser.add_option('-k', '--keyword', type='string', help='Only run tests whose function name contains this keyword')
    (options, args) = parser.parse_args()
    if args:
        parser.error('Unexpected positional arguments: {}'.format(' '.join(args)))
        return
    dslx_path = options.dslx_path.split(':') if options.dslx_path else None
    config = build_presubmit_config(Path(__file__).resolve().parent, tuple(dslx_path) if dslx_path else None)

    to_run = TO_RUN
    if options.keyword:
        to_run = [f for f in TO_RUN if options.keyword in f.__name__]

    failures: List[Tuple[str, str]] = []
    for f in to_run:
        print('-' * 80)
        print('Executing', f.__name__)
        print('-' * 80)

        try:
            f(config)
        except Exception as e:
            err_msg = str(e)
            failures.append((f.__name__, err_msg))
            print("FAILED presubmit step:", f.__name__)
            print("Reason:", err_msg)
            # Continue to gather all failures so we can summarize at the end.

    if failures:
        print('\n' + '=' * 80)
        print('Presubmit summary: FAIL ({} failing step(s))'.format(len(failures)))
        for name, msg in failures:
            print('- {}: {}'.format(name, msg))
        print('=' * 80)
        sys.exit(1)
    else:
        print('\n' + '=' * 80)
        print('Presubmit summary: OK (all {} step(s) passed)'.format(len(to_run)))
        print('=' * 80)

if __name__ == '__main__':
    main()
