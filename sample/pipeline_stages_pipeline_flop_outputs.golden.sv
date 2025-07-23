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
  input wire input_valid,
  input wire [31:0] x,
  output wire [31:0] out,
  output wire output_valid
);
  reg [31:0] p0_x;
  reg p0_valid;
  always_ff @ (posedge clk) begin
    p0_x <= input_valid ? x : p0_x;
    p0_valid <= rst ? 1'b0 : input_valid;
  end
  wire [31:0] stage0_out_comb;
  foo_cycle0 foo_cycle0_i (
    .x(p0_x),
    .out(stage0_out_comb)
  );
  reg [31:0] p1_out;
  reg p1_valid;
  always_ff @ (posedge clk) begin
    p1_out <= p0_valid ? stage0_out_comb : p1_out;
    p1_valid <= rst ? 1'b0 : p0_valid;
  end
  assign out = p1_out;
  assign output_valid = p1_valid;
endmodule

