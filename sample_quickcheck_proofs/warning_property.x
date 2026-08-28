// SPDX-License-Identifier: Apache-2.0

// QuickCheck bodies suppress unused-local warnings, so exercise warning policy
// in a regular helper that is reached from the property.
fn identity_with_warning(x: u8) -> u8 {
    let unused = x;
    x
}

#[quickcheck]
fn property_with_warning(x: u8) -> bool { identity_with_warning(x) == x }
