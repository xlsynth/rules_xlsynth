// SPDX-License-Identifier: Apache-2.0

// Note: this path is relative to repository root.
import sample.imported;

fn main() -> u32 { (imported::MOL << 1) >> 1 }

#[test]
fn test_main() {
    let got = main();
    trace_fmt!("got: {}", got);
    assert_eq(got, u32:42);
}

#[quickcheck]
fn quickcheck_main(x: u32) -> bool { main() == imported::MOL }
