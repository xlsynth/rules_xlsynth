module __sample__main(
  input wire clk,
  input wire rst,
  input wire input_valid,
  output wire output_valid,
  output wire [31:0] out
);
  // ===== Pipe stage 0:

  // Registers for pipe stage 0:
  reg p0_valid;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p0_valid <= 1'h0;
    end else begin
      p0_valid <= input_valid;
    end
  end

  // ===== Pipe stage 1:
  wire [31:0] p1_literal_9_comb;
  wire p1_load_en_comb;
  assign p1_literal_9_comb = 32'h0000_002a;
  assign p1_load_en_comb = p0_valid | rst;

  // Registers for pipe stage 1:
  reg p1_valid;
  reg [31:0] p1_literal_9;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p1_valid <= 1'h0;
      p1_literal_9 <= 32'h0000_0000;
    end else begin
      p1_valid <= p0_valid;
      p1_literal_9 <= p1_load_en_comb ? p1_literal_9_comb : p1_literal_9;
    end
  end
  assign output_valid = p1_valid;
  assign out = p1_literal_9;
endmodule

