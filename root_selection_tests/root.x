// SPDX-License-Identifier: Apache-2.0

import root_selection_tests.support;

pub struct RootData { value: u32 }

pub fn main(x: u32) -> u32 { x + support::value() }

fn root_cycle0(x: u32) -> u32 { main(x) }

#[test]
fn root_imports_work() { assert_eq(main(u32:1), u32:314160); }

#[quickcheck]
fn root_property(x: u32) -> bool { main(x) == x + u32:314159 }
