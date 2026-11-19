// SPDX-License-Identifier: Apache-2.0

pub fn main(x: u32) -> u32 { x + u32:0 }

// Conversion must continue excluding test functions.
#[test]
fn arithmetic_test() { assert_eq(main(u32:7), u32:7); }
