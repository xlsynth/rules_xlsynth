# SPDX-License-Identifier: Apache-2.0

"""Regression checks for presubmit proof evidence and warning expectations."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

import run_presubmit


class PresubmitTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config = run_presubmit.PresubmitConfig(Path(self.tempdir.name), None, '0.66.0', '0.54.7')
        self.target = '//sample:proof'
        self.output_dir = run_presubmit._test_output_dir(self.config, self.target)
        self.output_dir.mkdir(parents = True)

    def write_report(self, report, zipped = False, filename = 'ir_equiv.json'):
        encoded = json.dumps(report)
        if zipped:
            with zipfile.ZipFile(str(self.output_dir / 'outputs.zip'), 'w') as archive:
                archive.writestr(filename, encoded)
        else:
            (self.output_dir / filename).write_text(encoded, encoding = 'utf-8')

    def test_equivalent_result(self):
        self.write_report({'success': True, 'error_str': None})
        run_presubmit._check_ir_equiv_report(self.config, self.target, True)

    def test_counterexample_in_plain_and_archived_reports(self):
        model = ('lhs_inputs: [FnInput { name: "x", value: bits[32]:0 }], '
                 'rhs_inputs: [FnInput { name: "x", value: bits[32]:0 }], '
                 'lhs_output: FnOutput { value: bits[32]:1, assertion_violation: None }, '
                 'rhs_output: FnOutput { value: bits[32]:2, assertion_violation: None }')
        for zipped in (False, True):
            with self.subTest(zipped = zipped):
                for path in self.output_dir.iterdir():
                    path.unlink()
                self.write_report({'success': False, 'error_str': model}, zipped = zipped)
                run_presubmit._check_ir_equiv_report(self.config, self.target, False)

    def test_rejects_solver_errors_inconclusive_missing_models_and_success(self):
        for report in (
                {'success': False, 'error_str': 'solver unavailable'},
                {'success': False, 'error_str': 'solver returned unknown'},
                {'success': False, 'error_str': 'lhs_inputs: [], rhs_inputs: []'},
                {'success': False, 'error_str': None},
                {'success': True, 'error_str': None},
                {}):
            with self.subTest(report = report):
                self.write_report(report)
                with self.assertRaises(ValueError):
                    run_presubmit._check_ir_equiv_report(self.config, self.target, False)

    def test_netlist_inequivalence_requires_lean_to_run_and_reject_the_proof(self):
        report = {'status': 'failed', 'lean': {'status': 'failed', 'error': 'could not start Lean'}}
        for code in (1, 3):
            with self.subTest(bazel_exit = code):
                failure = subprocess.CalledProcessError(code, ['bazel'])
                with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = [None, failure]):
                    with mock.patch.object(run_presubmit, '_read_test_json_report', return_value = report) as read:
                        with self.assertRaises(ValueError):
                            run_presubmit.run_netlist_lean_equiv_tests(self.config)
                        # Bazel can leave an earlier report behind on a build failure.
                        self.assertEqual(read.called, code == 3)

    def test_missing_report_is_not_accepted(self):
        with self.assertRaises(FileNotFoundError):
            run_presubmit._check_ir_equiv_report(self.config, self.target, False)

    def test_build_failure_cannot_reuse_an_earlier_report(self):
        failure = subprocess.CalledProcessError(1, ['bazel'], stderr = 'build failed before test execution')
        with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = [None, failure]):
            with mock.patch.object(run_presubmit, '_check_ir_equiv_report') as check:
                with self.assertRaises(ValueError):
                    run_presubmit.run_sample_nonequiv_ir(self.config)
        check.assert_called_once_with(self.config, '//sample_nonequiv_ir:add_one_ir_prove_equiv_test', True)

    def test_quickcheck_plain_and_archived_reports(self):
        report = {
            'success': False,
            'tests': [
                {'name': 'passing', 'success': True},
                {'name': 'failing', 'success': False,
                 'counterexample': 'inputs: [x = 0], output: false, assertion_violation: Some("failed")'},
            ],
        }
        for zipped in (False, True):
            with self.subTest(zipped = zipped):
                for path in self.output_dir.iterdir():
                    path.unlink()
                self.write_report(report, zipped = zipped, filename = 'quickcheck.json')
                run_presubmit._check_quickcheck_report(
                    self.config, self.target, {'passing': True, 'failing': False},
                    assertion_failure = 'failing',
                )

    def test_quickcheck_rejects_missing_duplicate_or_inconsistent_results(self):
        passing = {'name': 'passing', 'success': True}
        for report in (
                ['not an object'], {}, {'success': True, 'tests': []},
                {'success': True, 'tests': [passing, passing]},
                {'success': True, 'tests': [{'name': 'other', 'success': True}]},
                {'success': True, 'tests': [{'name': 'passing', 'success': 'true'}]},
                {'success': False, 'tests': [passing]}):
            with self.subTest(report = report):
                self.write_report(report, filename = 'quickcheck.json')
                with self.assertRaises(ValueError):
                    run_presubmit._check_quickcheck_report(self.config, self.target, {'passing': True})

    def test_quickcheck_requires_concrete_counterexamples_and_assertions(self):
        for counterexample in (None, 'solver error', 'inputs: []', 'inputs: [], output: false'):
            with self.subTest(counterexample = counterexample):
                self.write_report({
                    'success': False,
                    'tests': [{'name': 'failing', 'success': False, 'counterexample': counterexample}],
                }, filename = 'quickcheck.json')
                with self.assertRaises(ValueError):
                    run_presubmit._check_quickcheck_report(
                        self.config, self.target, {'failing': False}, assertion_failure = 'failing',
                    )

    def test_quickcheck_build_failure_cannot_reuse_an_earlier_report(self):
        failure = subprocess.CalledProcessError(1, ['bazel'], stderr = 'build failed before test execution')
        with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = failure):
            with mock.patch.object(run_presubmit, '_check_quickcheck_report') as check:
                with self.assertRaises(ValueError):
                    run_presubmit._expect_quickcheck_failure(self.config, self.target, {'failing': False})
        check.assert_not_called()

    def test_warning_then_disabled_warning(self):
        failure = subprocess.CalledProcessError(1, ['bazel'], stderr = 'Definition of `x` is not used in function `main`')
        with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = [failure, None]) as run:
            run_presubmit.run_sample_disabling_warning(self.config)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args[1]['more_action_env'], {'XLSYNTH_DSLX_DISABLE_WARNINGS': 'unused_definition'})

    def test_conversion_failure_accepts_diagnostic_on_stdout_or_stderr(self):
        diagnostic = 'Definition of `unused` is not used in function `warning_main`'
        for stream in ('output', 'stderr'):
            with self.subTest(stream = stream):
                failure = subprocess.CalledProcessError(1, ['bazel'], **{stream: diagnostic})
                with mock.patch.object(run_presubmit, 'bazel_build_opt', side_effect = failure):
                    run_presubmit._expect_dslx_to_ir_failure(self.config, '//dslx_to_ir_tests:warning_ir', diagnostic)

    # Negative test: A target name echoed by --subcommands is not a diagnostic.
    def test_conversion_failure_rejects_success_wrong_status_and_unrelated_errors(self):
        diagnostic = 'Entry "DoesNotExist" is not present in DSLX module'
        for outcome in (
                None,
                subprocess.CalledProcessError(1, ['bazel'], stderr = 'missing tool'),
                subprocess.CalledProcessError(1, ['bazel'], stderr = 'ir_converter_main --top=DoesNotExist'),
                subprocess.CalledProcessError(2, ['bazel'], stderr = diagnostic),
                subprocess.CalledProcessError(3, ['bazel'], stderr = diagnostic)):
            with self.subTest(outcome = outcome):
                with mock.patch.object(run_presubmit, 'bazel_build_opt', side_effect = [outcome]):
                    with self.assertRaises(ValueError):
                        run_presubmit._expect_dslx_to_ir_failure(self.config, '//dslx_to_ir_tests:missing_top_ir', diagnostic)

    def test_conversion_presubmit_runs_both_suites_and_warning_controls(self):
        missing = subprocess.CalledProcessError(1, ['bazel'], stderr = 'Entry "DoesNotExist" is not present in DSLX module')
        warning = subprocess.CalledProcessError(1, ['bazel'], stderr = 'is not used in function `warning_main`')
        with mock.patch.object(run_presubmit, 'bazel_test_opt') as tests:
            with mock.patch.object(run_presubmit, 'bazel_build_opt', side_effect = [missing, warning, warning, None]) as builds:
                run_presubmit.run_dslx_to_ir_tests(self.config)
        tests.assert_called_once_with(
            ('//dslx_to_ir_tests:conversion_tests', '//dslx_to_ir_tests:conversion_analysis_tests'),
            self.config,
            dslx_path = ('dslx_to_ir_tests/import_root_a', 'dslx_to_ir_tests/import_root_b'),
        )
        self.assertEqual(builds.call_count, 4)
        self.assertEqual(builds.call_args_list[2][1]['more_action_env'], {'XLSYNTH_DSLX_ENABLE_WARNINGS': 'unused_definition'})
        self.assertEqual(builds.call_args_list[3][1]['more_action_env'], {'XLSYNTH_DSLX_DISABLE_WARNINGS': 'unused_definition'})
        self.assertTrue(all(call[1]['dslx_path'] == run_presubmit._CONVERSION_IMPORT_ROOTS for call in builds.call_args_list))

    # Negative test: A failed disabled-warning build must fail presubmit too.
    def test_conversion_presubmit_requires_disabled_warning_build_to_succeed(self):
        failure = subprocess.CalledProcessError(1, ['bazel'], stderr = 'missing import')
        with mock.patch.object(run_presubmit, 'bazel_test_opt'):
            with mock.patch.object(run_presubmit, '_expect_dslx_to_ir_failure'):
                with mock.patch.object(run_presubmit, 'bazel_build_opt', side_effect = failure):
                    with self.assertRaises(subprocess.CalledProcessError):
                        run_presubmit.run_dslx_to_ir_tests(self.config)

    # Negative test: Error handling rejects unexpected success and unrelated failures.
    def test_warning_check_rejects_unexpected_success_and_unrelated_failure(self):
        for check in (run_presubmit.run_sample_disabling_warning, run_presubmit.run_sample_dslx_test_warning_policy):
            for outcome in (None, subprocess.CalledProcessError(1, ['bazel'], stderr = 'missing tool')):
                with self.subTest(check = check.__name__, outcome = outcome):
                    with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = [outcome]):
                        with self.assertRaises(ValueError):
                            check(self.config)

    # Negative test: Error handling rejects logs without a completed property run.
    def test_dslx_test_warning_policy_requires_property_execution(self):
        target = '//sample_quickcheck_proofs:warning_suppressed_interpreter_test'
        test_log = run_presubmit._test_output_dir(self.config, target).parent / 'test.log'
        test_log.parent.mkdir(parents = True)
        failure = subprocess.CalledProcessError(
            3, ['bazel'], stderr = 'Definition of `unused` is not used in function `identity_with_warning`',
        )
        for output in ('', '[ RUN QUICKCHECK        ] property_with_warning\n', '[                    OK ] other_property\n'):
            with self.subTest(output = output):
                test_log.write_text(output, encoding = 'utf-8')
                with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = [failure, failure, None]):
                    with self.assertRaisesRegex(ValueError, 'Expected the interpreter to execute property_with_warning'):
                        run_presubmit.run_sample_dslx_test_warning_policy(self.config)


if __name__ == '__main__':
    unittest.main()
