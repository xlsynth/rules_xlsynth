module __main__add_mol(
  input wire clk,
  input wire [31:0] x,
  output wire [31:0] out
);
  // ===== Pipe stage 0:

  // Registers for pipe stage 0:
  reg [31:0] x__input_flop;
  always_ff @ (posedge clk) begin
    x__input_flop <= x;
  end

  // ===== Pipe stage 1:
  wire [30:0] p1_add_26_comb;
  wire [31:0] p1_concat_31_comb;
  assign p1_add_26_comb = x__input_flop[31:1] + 31'h0000_0015;
  assign p1_concat_31_comb = {p1_add_26_comb, x__input_flop[0]};

  // Registers for pipe stage 1:
  reg [31:0] out__output_flop;
  always_ff @ (posedge clk) begin
    out__output_flop <= p1_concat_31_comb;
  end
  assign out = out__output_flop;
endmodule

