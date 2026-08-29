module __sample__main(
  input wire clk,
  input wire rst,
  output wire output_valid,
  output wire [31:0] out
);
  // ===== Pipe stage 0:
  wire p0_stage_outputs_valid_0_comb;
  wire [31:0] p0_literal_25_comb;
  assign p0_stage_outputs_valid_0_comb = 1'h1;
  assign p0_literal_25_comb = 32'h0000_002a;

  // Registers for pipe stage 0:
  reg output_valid__output_flop;
  reg [31:0] out__output_flop;
  always_ff @ (posedge clk) begin
    out__output_flop <= p0_literal_25_comb;
  end
  always_ff @ (posedge clk) begin
    if (rst) begin
      output_valid__output_flop <= 1'h0;
    end else begin
      output_valid__output_flop <= p0_stage_outputs_valid_0_comb;
    end
  end
  assign output_valid = output_valid__output_flop;
  assign out = out__output_flop;
endmodule

