// SPDX-License-Identifier: Apache-2.0

// A small example that should trigger array‐index/invariant assertions when
// XLSYNTH_ADD_INVARIANT_ASSERTIONS=true.
fn f(x0: u3, x4: u6) -> u6 {
    {
        let x6: u6 = match x0 {
            u3:0x3 | u3:0x4 => x4,
            u3:0x2 => u6:0x2a,
            _ => u6:0x8,
        };
        x6
    }
}
