import { describe, expect, it } from "vitest";
import { SSEParser } from "./sse";

describe("SSEParser", () => {
  it("parses complete events", () => {
    const parser = new SSEParser();
    const events = parser.push('event: token\ndata: {"t":"Hi"}\n\nevent: done\ndata: {}\n\n');
    expect(events).toEqual([
      { event: "token", data: '{"t":"Hi"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("buffers events split across chunks", () => {
    const parser = new SSEParser();
    expect(parser.push("event: tok")).toEqual([]);
    expect(parser.push('en\ndata: {"t":"a')).toEqual([]);
    expect(parser.push('b"}\n\n')).toEqual([{ event: "token", data: '{"t":"ab"}' }]);
  });

  it("handles CRLF and comments, and defaults the event name", () => {
    const parser = new SSEParser();
    const events = parser.push(": keep-alive\r\ndata: hello\r\n\r\n");
    expect(events).toEqual([{ event: "message", data: "hello" }]);
  });

  it("flushes a trailing event without a blank line", () => {
    const parser = new SSEParser();
    parser.push("event: done\ndata: 1");
    expect(parser.flush()).toEqual([{ event: "done", data: "1" }]);
  });
});
