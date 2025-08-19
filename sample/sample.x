// SPDX-License-Identifier: Apache-2.0

// Note: this path is relative to repository root.
import sample.imported;

// nothing has changed
fn main() -> u32 { (imported::MOL << 1) >> 1 }

#[test]
fn test_main() {
    let got = main();
    trace_fmt!("got: {}", got);
    assert_eq(got, u32:42);
}

#[quickcheck]
fn quickcheck_main(x: u32) -> bool { main() == imported::MOL }

/// A function with a little bit more heft to it for gates analysis.
fn add_chain(a: u32, b: u32, c: u32, d: u32) -> u32 {
    let ab = a + b;
    let abc = ab + c;
    abc + d
}

#[test]
fn test_add_chain() { assert_eq(u32:10, add_chain(u32:1, u32:2, u32:3, u32:4)); }
