// SPDX-License-Identifier: Apache-2.0

import imported;  // note: no absolute path prefix to exercise the dslx_path functionality
import another;  // this one comes from a secondary DSLX path

fn add_mol(x: u32) -> u32 { x + imported::MOL }

#[test]
fn test_mol() {
    assert_eq(imported::MOL, u32:42);
    assert_eq(imported::MOL == another::PI, false);
}
