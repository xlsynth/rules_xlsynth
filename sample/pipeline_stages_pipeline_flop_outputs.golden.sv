module foo_cycle0(
  input wire [31:0] x,
  output wire [31:0] out
);
  wire [31:0] literal_5;
  wire [31:0] add_6;
  assign literal_5 = 32'h0000_0001;
  assign add_6 = x + literal_5;
  assign out = add_6;
endmodule
module foo(
  input wire clk,
  input wire rst,
  input wire [31:0] x,
  input wire input_valid,
  output wire [31:0] out,
  output wire output_valid
);
  wire [31:0] stage_0_out_comb;
  foo_cycle0 stage_0 (
    .x(x),
    .out(stage_0_out_comb)
  );
  reg [31:0] p0_out;
  reg p0_valid;
  always @ (posedge clk) begin
    p0_out <= input_valid ? stage_0_out_comb : p0_out;
    p0_valid <= rst ? 1'b0 : input_valid;
  end
  assign out = p0_out;
  assign output_valid = p0_valid;
endmodule

