module __sample__main(
  input wire clk,
  input wire input_valid,
  output wire output_valid,
  output wire [31:0] out
);
  // ===== Pipe stage 0:

  // Registers for pipe stage 0:
  reg p0_valid;
  always_ff @ (posedge clk) begin
    p0_valid <= input_valid;
  end

  // ===== Pipe stage 1:
  wire [31:0] p1_MOL_comb;
  assign p1_MOL_comb = 32'h0000_002a;

  // Registers for pipe stage 1:
  reg p1_valid;
  reg [31:0] p1_MOL;
  always_ff @ (posedge clk) begin
    p1_valid <= p0_valid;
    p1_MOL <= p0_valid ? p1_MOL_comb : p1_MOL;
  end
  assign output_valid = p1_valid;
  assign out = p1_MOL;
endmodule
