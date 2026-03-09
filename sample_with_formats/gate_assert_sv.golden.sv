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
  wire p0_load_en_comb;
  assign p0_load_en_comb = input_valid | rst;

  // Registers for pipe stage 0:
  reg p0_valid;
  reg p0_pred;
  reg p0_x;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p0_valid <= 1'h0;
      p0_pred <= 1'h0;
      p0_x <= 1'h0;
    end else begin
      p0_valid <= input_valid;
      p0_pred <= p0_load_en_comb ? pred : p0_pred;
      p0_x <= p0_load_en_comb ? x : p0_x;
    end
  end

  // ===== Pipe stage 1:
  wire p1_or_75_comb;
  wire gated;
  wire p1_load_en_comb;
  assign p1_or_75_comb = ~p0_valid | p0_x | rst;
  assign gated = p0_pred & p0_x;
  assign p1_load_en_comb = p0_valid | rst;

  // Registers for pipe stage 1:
  reg p1_valid;
  reg p1_gated;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p1_valid <= 1'h0;
      p1_gated <= 1'h0;
    end else begin
      p1_valid <= p0_valid;
      p1_gated <= p1_load_en_comb ? gated : p1_gated;
    end
  end
  assign output_valid = p1_valid;
  assign out = p1_gated;
  `ifdef ASSERT_ON
  __gate_assert_minimal__main_0_non_synth___gate_assert_minimal__main_should_be_one: assert property (@(posedge clk) disable iff ($sampled(rst !== 1'h0 || $isunknown(p1_or_75_comb))) p1_or_75_comb) else $fatal(0, "Assertion failure via assert! @ sample_with_formats/gate_assert_minimal.x:4:12-4:40");
  `endif  // ASSERT_ON
endmodule

