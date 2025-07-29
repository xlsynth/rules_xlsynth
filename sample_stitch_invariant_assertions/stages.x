// SPDX-License-Identifier: Apache-2.0

// Two-stage pipeline: first stage passes arguments along; second stage contains
// the match expression that becomes a priority-select in RTL, which should
// receive one-hot invariant assertions when enabled.

type T = (u3, u6);

fn foo_cycle0(x0: u3, x4: u6) -> T {
    (x0, x4)
}

fn foo_cycle1(t: T) -> u6 {
    let (x0, x4): T = t;
    let x6: u6 = match x0 {
        u3:0x3 | u3:0x4 => x4,
        u3:0x2 => u6:0x2a,
        _ => u6:0x8,
    };
    x6
}
