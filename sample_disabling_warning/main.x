// SPDX-License-Identifier: Apache-2.0

fn main() -> u32 {
    let x = u32:42;  // unused_definition
    // Equal-bound ranges are valid; this sample tests unused_definition.
    for (_i, accum) in u32:0..u32:0 {
        accum
    }(u32:64)
}
