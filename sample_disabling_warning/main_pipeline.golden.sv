module __main__main(
  input wire clk,
  output wire [31:0] out
);
  // ===== Pipe stage 0:
  wire [31:0] p0_literal_22_comb;
  assign p0_literal_22_comb = 32'h0000_0040;

  // Registers for pipe stage 0:
  reg [31:0] out__output_flop;
  always_ff @ (posedge clk) begin
    out__output_flop <= p0_literal_22_comb;
  end
  assign out = out__output_flop;
endmodule

