module noflops(
  input wire clk,
  output wire [31:0] out
);
  // ===== Pipe stage 0:
  assign out = 32'h0000_002a;
endmodule

