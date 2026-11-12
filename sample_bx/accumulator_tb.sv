// SPDX-License-Identifier: Apache-2.0

module accumulator_tb;
  logic clk = 0;
  logic rst;
  logic enable;
  logic [7:0] x;
  wire [7:0] out;

  accumulator dut (.clk(clk), .rst(rst), .enable(enable), .x(x), .out(out));

  task automatic cycle(
      input logic reset,
      input logic load,
      input logic [7:0] data,
      input logic [7:0] expected
  );
    rst = !reset;
    enable = load;
    x = data;
    #5 clk = 1;
    #1;
    if (out !== expected) $fatal(1, "Expected %0d, got %0d", expected, out);
    #4 clk = 0;
  endtask

  initial begin
    cycle(1, 0, 0, 0);
    cycle(0, 1, 4, 11);
    cycle(0, 1, 1, 19);
    cycle(0, 0, 91, 19);
    cycle(1, 1, 91, 0);
    $finish;
  end
endmodule
