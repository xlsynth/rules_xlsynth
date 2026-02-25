// SPDX-License-Identifier: Apache-2.0

#![feature(use_syntax)]

#[quickcheck]
fn always_fail_nullary() -> bool { false }

#[quickcheck]
fn always_fail(a: u1, b: u2) -> bool {
    let _touch_args = (a, b);
    false
}
