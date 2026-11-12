module extended_carry(
  input logic [7:0] lhs,
  input logic [7:0] rhs,
  input logic carry_in,
  output logic carry_out
);
  logic result;
  assign result = 1'({1'h0, lhs} + {1'h0, rhs} + {8'h00, carry_in} >> 8);
  assign carry_out = result;
endmodule
