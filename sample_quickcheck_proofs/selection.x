// SPDX-License-Identifier: Apache-2.0

#[quickcheck]
fn selected_alpha(x: u8) -> bool { (x ^ x) == u8:0 }

#[quickcheck]
fn selected_beta(x: u8) -> bool { x + u8:0 == x }

// Prefix/suffix matches must not leak through an exact or alternation filter.
#[quickcheck]
fn selected_alpha_suffix(_x: u8) -> bool { false }

#[quickcheck]
fn prefix_selected_beta(_x: u8) -> bool { false }
