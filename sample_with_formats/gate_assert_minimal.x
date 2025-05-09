// SPDX-License-Identifier: Apache-2.0

fn main(pred: bool, x: u1) -> u1 {
    assert!(x == u1:1, "should_be_one");
    let gated = gate!(pred, x);
    gated
}

#[test]
fn test_main_enabled() {
    let got = main(true, u1:1);
    assert_eq(got, u1:1);
}

#[test]
fn test_main_disabled() {
    let got = main(false, u1:1);
    assert_eq(got, u1:0);
}
