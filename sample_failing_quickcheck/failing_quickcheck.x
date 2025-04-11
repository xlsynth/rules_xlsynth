// SPDX-License-Identifier: Apache-2.0

#![feature(use_syntax)]

use sample_failing_quickcheck::simple_dependency_a::MyTupleA;
use sample_failing_quickcheck::simple_dependency_b::MyTupleB;

#[quickcheck]
fn always_fail_nullary() -> bool { false }

#[quickcheck]
fn always_fail(a: MyTupleA, b: MyTupleB) -> bool { false }
