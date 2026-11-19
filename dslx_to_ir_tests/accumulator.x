// SPDX-License-Identifier: Apache-2.0

pub proc Accumulator {
    input: chan<u32> in;
    output: chan<u32> out;

    config(input: chan<u32> in, output: chan<u32> out) { (input, output) }
    init { u32:0 }
    next(state: u32) {
        let (tok, value) = recv(join(), input);
        let state_next = state + value;
        send(tok, output, state_next);
        state_next
    }
}
