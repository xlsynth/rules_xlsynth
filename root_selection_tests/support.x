// SPDX-License-Identifier: Apache-2.0

import sample_expecting_dslx_path.subdir.another;

pub fn value() -> u32 { another::PI }

#[test]
fn support_passes() { assert_eq(value(), u32:314159); }
