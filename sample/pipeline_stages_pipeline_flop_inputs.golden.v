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
  assign out = stage_0_out_comb;
  assign output_valid = p0_valid;
endmodule

