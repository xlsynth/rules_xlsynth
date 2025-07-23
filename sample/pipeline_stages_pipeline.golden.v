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

module foo_cycle1(
  input wire [31:0] x,
  output wire [31:0] out
);
  wire [31:0] literal_8;
  wire [31:0] add_9;
  assign literal_8 = 32'h0000_0001;
  assign add_9 = x + literal_8;
  assign out = add_9;
endmodule
module foo(
  input wire clk,
  input wire [31:0] x,
  output wire [31:0] out
);
  reg [31:0] p0_x;
  always @ (posedge clk) begin
    p0_x <= x;
  end
  wire [31:0] stage_0_out_comb;
  foo_cycle0 stage_0 (
    .x(p0_x),
    .out(stage_0_out_comb)
  );
  reg [31:0] p1_x;
  always @ (posedge clk) begin
    p1_x <= stage_0_out_comb;
  end
  wire [31:0] stage_1_out_comb;
  foo_cycle1 stage_1 (
    .x(p1_x),
    .out(stage_1_out_comb)
  );
  reg [31:0] p2_out;
  always @ (posedge clk) begin
    p2_out <= stage_1_out_comb;
  end
  assign out = p2_out;
endmodule

