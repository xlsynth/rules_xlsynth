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

  // Registers for pipe stage 1:
  reg p1_valid;
  always_ff @ (posedge clk) begin
    if (rst) begin
      p1_valid <= 1'h0;
    end else begin
      p1_valid <= p0_valid;
    end
  end
  assign output_valid = p1_valid;
  assign out = 32'h0000_002a;
endmodule

