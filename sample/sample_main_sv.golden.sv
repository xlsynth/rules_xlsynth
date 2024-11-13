module __sample__main(
  input wire clk,
  output wire [31:0] out
);
  // ===== Pipe stage 0:
  wire [31:0] p0_MOL_comb;
  assign p0_MOL_comb = 32'h0000_002a;

  // Registers for pipe stage 0:
  reg [31:0] p1_MOL;
  always_ff @ (posedge clk) begin
    p1_MOL <= p0_MOL_comb;
  end
  assign out = p1_MOL;
endmodule

