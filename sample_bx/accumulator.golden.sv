module _bx_sample_bx_lib_stages_accumulate(
  input logic clk,
  input logic rst,
  input logic enable,
  input logic [7:0] increment,
  output logic [7:0] out
);
  logic [7:0] total;
  logic [7:0] add_14;
  assign add_14 = total + increment;
  always_ff @ (posedge clk) begin
    if (!rst) begin
      total <= 8'h00;
    end else begin
      total <= enable ? add_14 : total;
    end
  end
  assign out = total;
endmodule
module accumulator(
  input logic clk,
  input logic rst,
  input logic enable,
  input logic [7:0] x,
  output logic [7:0] out
);
  logic [7:0] total_out;
  logic [31:0] i;
  logic [31:0] i__1;
  logic [7:0] add_59;
  logic [31:0] i__2;
  logic [7:0] add_62;
  logic [7:0] add_64;
  logic [7:0] add_26;
  assign i = 32'h0000_0000 + 32'h0000_0001;
  assign i__1 = 32'h0000_0001 + 32'h0000_0001;
  assign add_59 = x + i[7:0];
  assign i__2 = 32'h0000_0002 + 32'h0000_0001;
  assign add_62 = add_59 + i__1[7:0];
  assign add_64 = add_62 + i__2[7:0];
  assign add_26 = add_64 + 8'h01;
  assign out = total_out;
  _bx_sample_bx_lib_stages_accumulate total (
    .clk(clk),
    .rst(rst),
    .enable(enable),
    .increment(add_26),
    .out(total_out)
  );
endmodule
