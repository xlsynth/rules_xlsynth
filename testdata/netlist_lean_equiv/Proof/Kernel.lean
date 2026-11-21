-- SPDX-License-Identifier: Apache-2.0

import Target

theorem Kernel.equivalent : Target.Equivalent := by
  unfold Target.Equivalent XlsynthLean.Aig.Circuit.Equivalent
  simp only [← XlsynthLean.Aig.Circuit.eval_eq_denote]
  decide +kernel
