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
  input wire rst,
  input wire input_valid,
  input wire [31:0] x,
  output wire output_valid,
  output wire [31:0] out
);
  reg [31:0] p0_x;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p0_x <= 32'h0000_0000;
    end else if (input_valid) begin
      p0_x <= x;
    end
  end
  wire [31:0] p1_next;
  foo_cycle0 foo_cycle0_i (
    .x(p0_x),
    .out(p1_next)
  );
  reg [31:0] p1;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p1 <= 32'h0000_0000;
    end else begin
      p1 <= p1_next;
    end
  end
  wire [31:0] p2_next;
  foo_cycle1 foo_cycle1_i (
    .x(p1),
    .out(p2_next)
  );
  reg [31:0] p2;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p2 <= 32'h0000_0000;
    end else begin
      p2 <= p2_next;
    end
  end
  assign out = p2;
  assign output_valid = input_valid;
endmodule 