// SPDX-License-Identifier: Apache-2.0

#[quickcheck]
fn addition_commutes(x: u8, y: u8) -> bool { x + y == y + x }

#[quickcheck]
fn xor_cancels(x: u8, y: u8) -> bool { ((x ^ y) ^ y) == x }

#[quickcheck]
fn assertion_holds(x: u8) -> bool {
    assert_eq(x + u8:0, x);
    true
}
