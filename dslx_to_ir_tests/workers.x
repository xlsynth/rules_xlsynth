// SPDX-License-Identifier: Apache-2.0

type Payload = (u32, bool);

proc Worker<INCREMENT: u32> {
    input: chan<Payload> in;
    output: chan<Payload> out;

    config(input: chan<Payload> in, output: chan<Payload> out) { (input, output) }
    init { () }
    next(state: ()) {
        let (tok, (value, valid)) = recv(join(), input);
        send(tok, output, (value + INCREMENT, valid));
        state
    }
}

pub proc Network {
    config(input: chan<Payload> in, output: chan<Payload> out) {
        let (middle_s, middle_r) = chan<Payload>("middle");
        spawn Worker<u32:3>(input, middle_s);
        spawn Worker<u32:5>(middle_r, output);
        ()
    }
    init { () }
    next(state: ()) { state }
}
