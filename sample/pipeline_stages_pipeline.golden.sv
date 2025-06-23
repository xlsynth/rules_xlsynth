module foo_cycle0(
  input wire clk,
  input wire [31:0] x,
  output wire [31:0] out
);
  // ===== Pipe stage 0:

  // Registers for pipe stage 0:
  reg [31:0] p0_x;
  always_ff @ (posedge clk) begin
    p0_x <= x;
  end

  // ===== Pipe stage 1:
  wire [31:0] p1_literal_7_comb;
  wire [31:0] p1_add_8_comb;
  assign p1_literal_7_comb = 32'h0000_0001;
  assign p1_add_8_comb = p0_x + p1_literal_7_comb;
  assign out = p1_add_8_comb;
endmodule

module foo_cycle1(
  input wire clk,
  input wire [31:0] x,
  output wire [31:0] out
);
  // ===== Pipe stage 0:

  // Registers for pipe stage 0:
  reg [31:0] p0_x;
  always_ff @ (posedge clk) begin
    p0_x <= x;
  end

  // ===== Pipe stage 1:
  wire [31:0] p1_literal_10_comb;
  wire [31:0] p1_add_11_comb;
  assign p1_literal_10_comb = 32'h0000_0001;
  assign p1_add_11_comb = p0_x + p1_literal_10_comb;

  // Registers for pipe stage 1:
  reg [31:0] p1_add_11;
  always_ff @ (posedge clk) begin
    p1_add_11 <= p1_add_11_comb;
  end
  assign out = p1_add_11;
endmodule
module foo(
  input wire [31:0] x,
  output wire [31:0] out
);
  wire [31:0] stage0_out;
  foo_cycle0 foo_cycle0_i (
    .x(x),
    .out(stage0_out)
  );
  wire [31:0] final_out;
  foo_cycle1 foo_cycle1_i (
    .x(stage0_out),
    .out(final_out)
  );
  assign out = final_out;
endmodule

