module foo_cycle0(
  input wire [31:0] x,
  output wire [31:0] out
);
  wire [31:0] literal_11;
  wire [31:0] add_14;
  assign literal_11 = 32'h0000_0001;
  assign add_14 = x + literal_11;
  assign out = add_14;
endmodule

module foo_cycle1(
  input wire [31:0] x,
  output wire [31:0] out
);
  wire [31:0] literal_14;
  wire [31:0] add_17;
  assign literal_14 = 32'h0000_0001;
  assign add_17 = x + literal_14;
  assign out = add_17;
endmodule
module foo(
  input wire clk,
  input wire rst,
  input wire [31:0] x,
  input wire input_valid,
  output wire [31:0] out,
  output wire output_valid
);
  reg [31:0] p0_x;
  reg p0_valid;
  always @ (posedge clk) begin
    p0_x <= input_valid ? x : p0_x;
    p0_valid <= rst ? 1'b0 : input_valid;
  end
  wire [31:0] stage_0_out_comb;
  foo_cycle0 stage_0 (
    .x(p0_x),
    .out(stage_0_out_comb)
  );
  reg [31:0] p1_x;
  reg p1_valid;
  always @ (posedge clk) begin
    p1_x <= p0_valid ? stage_0_out_comb : p1_x;
    p1_valid <= rst ? 1'b0 : p0_valid;
  end
  wire [31:0] stage_1_out_comb;
  foo_cycle1 stage_1 (
    .x(p1_x),
    .out(stage_1_out_comb)
  );
  reg [31:0] p2_out;
  reg p2_valid;
  always @ (posedge clk) begin
    p2_out <= p1_valid ? stage_1_out_comb : p2_out;
    p2_valid <= rst ? 1'b0 : p1_valid;
  end
  assign out = p2_out;
  assign output_valid = p2_valid;
endmodule

