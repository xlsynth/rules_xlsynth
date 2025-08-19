// SPDX-License-Identifier: Apache-2.0

// Note: this path is relative to repository root.
import sample.imported;
import sample.sample;

#[test]
fn test_sample_main_via_src() { assert_eq(sample::main(), imported::MOL); }
