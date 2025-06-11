// SPDX-License-Identifier: Apache-2.0

// Slice exactly at the 32-bit limit – accepted in type inference v1, but
// rejected when XLSYNTH_TYPE_INFERENCE_V2=true.
fn slice_at_limit(x: u32) -> u32 {
    x[32 +: u32]
}
