module byte_sum(
  input wire clk,
  input wire [7:0] a,
  input wire [7:0] b,
  output wire [7:0] out
);
  // ===== Pipe stage 0:
  wire [7:0] p0_add_18_comb;
  assign p0_add_18_comb = a + b;

  // Registers for pipe stage 0:
  reg [7:0] out__output_flop;
  always_ff @ (posedge clk) begin
    out__output_flop <= p0_add_18_comb;
  end
  assign out = out__output_flop;
endmodule

