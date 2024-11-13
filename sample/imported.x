// SPDX-License-Identifier: Apache-2.0

import std;

pub const MOL = u32:42;

pub struct MyStruct { some_field: u7 }

#[test]
fn test_mol_is_even() { assert_eq(MOL % u32:2 == u32:0, true); }

#[test]
fn test_mol_clog2() { assert_eq(std::clog2(MOL), u32:6); }
