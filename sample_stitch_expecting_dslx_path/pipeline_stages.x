
// SPDX-License-Identifier: Apache-2.0

import imported;  // resolved via XLSYNTH_DSLX_PATH
import another;   // comes from secondary path

fn foo_cycle0(x: u32) -> u32 { x + imported::MOL }

fn foo_cycle1(x: u32) -> u32 { x + another::PI }

fn foo(x: u32) -> u32 { x + imported::MOL + another::PI }
