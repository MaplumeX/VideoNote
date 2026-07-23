import { describe, expect, it } from "vitest";
import { createSSEParser, type SSEMessage } from "./sseParser";

function parseChunks(chunks: string[]): SSEMessage[] {
  const messages: SSEMessage[] = [];
  const parser = createSSEParser((message) => messages.push(message));
  chunks.forEach((chunk) => parser.feed(chunk));
  parser.end();
  return messages;
}

describe("createSSEParser", () => {
  it("parses CRLF events at every possible network chunk boundary", () => {
    const stream = [
      "event: progress\r\n",
      "data: {\"stage\":\"pending\"}\r\n",
      "\r\n",
      "event: complete\r\n",
      "data: {\"markdown\":\"笔记\"}\r\n",
      "\r\n",
    ].join("");
    const expected = [
      { event: "progress", data: "{\"stage\":\"pending\"}" },
      { event: "complete", data: "{\"markdown\":\"笔记\"}" },
    ];

    for (let boundary = 0; boundary <= stream.length; boundary += 1) {
      expect(parseChunks([
        stream.slice(0, boundary),
        stream.slice(boundary),
      ])).toEqual(expected);
    }
    expect(parseChunks([...stream])).toEqual(expected);
  });

  it("joins multiple data fields and flushes an unterminated final event", () => {
    expect(parseChunks([
      ": keepalive\n",
      "event: custom\n",
      "data: first\n",
      "data: second",
    ])).toEqual([
      { event: "custom", data: "first\nsecond" },
    ]);
  });
});
