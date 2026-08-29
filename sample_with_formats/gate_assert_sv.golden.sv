module __gate_assert_minimal__main(
  input wire clk,
  input wire rst,
  input wire input_valid,
  input wire pred,
  input wire x,
  output wire output_valid,
  output wire out
);
  // ===== Pipe stage 0:

  // Registers for pipe stage 0:
  reg input_valid__input_flop;
  reg pred__input_flop;
  reg x__input_flop;
  always_ff @ (posedge clk) begin
    if (rst) begin
      input_valid__input_flop <= 1'h0;
      pred__input_flop <= 1'h0;
      x__input_flop <= 1'h0;
    end else begin
      input_valid__input_flop <= input_valid;
      pred__input_flop <= input_valid ? pred : pred__input_flop;
      x__input_flop <= input_valid ? x : x__input_flop;
    end
  end

  // ===== Pipe stage 1:
  wire p1_or_84_comb;
  wire p1_gated_comb;
  assign p1_or_84_comb = ~input_valid__input_flop | x__input_flop | rst;
  br_gate_buf gated_p1_gated_comb(.in(x__input_flop), .out(p1_gated_comb));

  // Registers for pipe stage 1:
  reg output_valid__output_flop;
  reg out__output_flop;
  always_ff @ (posedge clk) begin
    if (rst) begin
      output_valid__output_flop <= 1'h0;
      out__output_flop <= 1'h0;
    end else begin
      output_valid__output_flop <= input_valid__input_flop;
      out__output_flop <= input_valid__input_flop ? p1_gated_comb : out__output_flop;
    end
  end
  assign output_valid = output_valid__output_flop;
  assign out = out__output_flop;
  `ifdef ASSERT_ON
  `BR_ASSERT(__gate_assert_minimal__main_0_non_synth___gate_assert_minimal__main_should_be_one, p1_or_84_comb)
  `endif  // ASSERT_ON
endmodule

