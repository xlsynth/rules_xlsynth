-- SPDX-License-Identifier: Apache-2.0

import Target

theorem Decision.equivalent : Target.Equivalent := by
  unfold Target.Equivalent XlsynthLean.Aig.Circuit.Equivalent
  native_decide
