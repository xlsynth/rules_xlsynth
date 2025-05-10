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
  wire p1_gated_comb;
  wire p1_load_en_comb;
  br_gate_buf gated_p1_gated_comb(.in(p0_x), .out(p1_gated_comb));
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
      p1_gated <= p1_load_en_comb ? p1_gated_comb : p1_gated;
    end
  end
  assign output_valid = p1_valid;
  assign out = p1_gated;
  `ifdef ASSERT_ON
  `BR_ASSERT(should_be_one, p0_x)
  `endif  // ASSERT_ON
endmodule

