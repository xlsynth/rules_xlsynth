// SPDX-License-Identifier: Apache-2.0

pub const MOL = u32:42;

#[test]
fn test_mol_is_even() {
    assert_eq(MOL % u32:2 == u32:0, true);
}
