// SPDX-License-Identifier: Apache-2.0

pub fn add_step(x: u8) -> u8 {
    for (i, sum): (u32, u8) in u32:1..u32:4 {
        sum + i as u8
    }(x)
}
