module __main__add_mol(
  input wire clk,
  input wire [31:0] x,
  output wire [31:0] out
);
  // ===== Pipe stage 0:

  // Registers for pipe stage 0:
  reg [31:0] p0_x;
  always_ff @ (posedge clk) begin
    p0_x <= x;
  end

  // ===== Pipe stage 1:
  wire [30:0] p1_add_18_comb;
  wire [31:0] p1_concat_20_comb;
  assign p1_add_18_comb = p0_x[31:1] + 31'h0000_0015;
  assign p1_concat_20_comb = {p1_add_18_comb, p0_x[0]};

  // Registers for pipe stage 1:
  reg [31:0] p1_concat_20;
  always_ff @ (posedge clk) begin
    p1_concat_20 <= p1_concat_20_comb;
  end
  assign out = p1_concat_20;
endmodule

