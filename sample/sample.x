// SPDX-License-Identifier: Apache-2.0

// Note: this path is relative to repository root.
import sample.imported;

fn main() -> u32 { (imported::MOL << 1) >> 1 }

#[test]
fn test_main() { assert_eq(main(), u32:42) }
