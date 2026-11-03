-- SPDX-License-Identifier: Apache-2.0
import Target

theorem identity_equivalent : Target.Equivalent := by
  intro x
  change x = x + 0
  simp
