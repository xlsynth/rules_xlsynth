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
        self.output_dir = run_presubmit._ir_equiv_output_dir(self.config, self.target)
        self.output_dir.mkdir(parents = True)

    def write_report(self, report, zipped = False):
        encoded = json.dumps(report)
        if zipped:
            with zipfile.ZipFile(str(self.output_dir / 'outputs.zip'), 'w') as archive:
                archive.writestr('ir_equiv.json', encoded)
        else:
            (self.output_dir / 'ir_equiv.json').write_text(encoded, encoding = 'utf-8')

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

    def test_warning_then_disabled_warning(self):
        failure = subprocess.CalledProcessError(1, ['bazel'], stderr = 'Definition of `x` is not used in function `main`')
        with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = [failure, None]) as run:
            run_presubmit.run_sample_disabling_warning(self.config)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args[1]['more_action_env'], {'XLSYNTH_DSLX_DISABLE_WARNINGS': 'unused_definition'})

    def test_warning_check_rejects_unexpected_success_and_unrelated_failure(self):
        for outcome in (None, subprocess.CalledProcessError(1, ['bazel'], stderr = 'missing tool')):
            with self.subTest(outcome = outcome):
                with mock.patch.object(run_presubmit, 'bazel_test_opt', side_effect = [outcome]):
                    with self.assertRaises(ValueError):
                        run_presubmit.run_sample_disabling_warning(self.config)


if __name__ == '__main__':
    unittest.main()
