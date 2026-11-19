// SPDX-License-Identifier: Apache-2.0

import conversion_left;
import conversion_right;
import std;

pub fn main(x: u32) -> bool {
    std::is_pow2(conversion_left::left(x) + conversion_right::right(x))
}
