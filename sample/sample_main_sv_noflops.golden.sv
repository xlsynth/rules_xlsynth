module noflops(
  input wire clk,
  output wire [31:0] out
);
  // ===== Pipe stage 0:
  wire [31:0] p0_MOL_comb;
  assign p0_MOL_comb = 32'h0000_002a;
  assign out = p0_MOL_comb;
endmodule

