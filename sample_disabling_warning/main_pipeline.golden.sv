module __main__main(
  input wire clk,
  output wire [31:0] out
);
  // ===== Pipe stage 0:
  wire [31:0] p0_literal_13_comb;
  assign p0_literal_13_comb = 32'h0000_0040;

  // Registers for pipe stage 0:
  reg [31:0] p1_literal_13;
  always_ff @ (posedge clk) begin
    p1_literal_13 <= p0_literal_13_comb;
  end
  assign out = p1_literal_13;
endmodule

