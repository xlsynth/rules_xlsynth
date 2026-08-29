// SPDX-License-Identifier: Apache-2.0

// A true return value does not excuse a failing in-function assertion.
#[quickcheck]
fn assertion_that_can_fail(x: u8) -> bool {
    assert_eq(x, u8:0);
    true
}
