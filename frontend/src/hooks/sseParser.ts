export interface SSEMessage {
  event: string;
  data: string;
}

export interface SSEParser {
  feed(chunk: string): void;
  end(): void;
}

/**
 * Incrementally parses an SSE stream. Parser state is intentionally retained
 * between feed() calls because network chunks can split at any character.
 */
export function createSSEParser(onMessage: (message: SSEMessage) => void): SSEParser {
  let buffer = "";
  let event = "";
  let dataLines: string[] = [];

  const dispatch = () => {
    if (dataLines.length > 0) {
      onMessage({ event: event || "message", data: dataLines.join("\n") });
    }
    event = "";
    dataLines = [];
  };

  const processLine = (line: string) => {
    if (line === "") {
      dispatch();
      return;
    }
    if (line.startsWith(":")) return;

    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") {
      event = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  };

  const drain = (endOfStream: boolean) => {
    let offset = 0;
    while (offset < buffer.length) {
      const carriageReturn = buffer.indexOf("\r", offset);
      const lineFeed = buffer.indexOf("\n", offset);
      let lineEnd = -1;

      if (carriageReturn !== -1 && lineFeed !== -1) {
        lineEnd = Math.min(carriageReturn, lineFeed);
      } else {
        lineEnd = Math.max(carriageReturn, lineFeed);
      }
      if (lineEnd === -1) break;

      if (buffer[lineEnd] === "\r" && lineEnd === buffer.length - 1 && !endOfStream) {
        break;
      }

      processLine(buffer.slice(offset, lineEnd));
      offset = lineEnd + (
        buffer[lineEnd] === "\r" && buffer[lineEnd + 1] === "\n" ? 2 : 1
      );
    }

    buffer = buffer.slice(offset);
    if (endOfStream) {
      if (buffer) processLine(buffer);
      buffer = "";
      dispatch();
    }
  };

  return {
    feed(chunk: string) {
      buffer += chunk;
      drain(false);
    },
    end() {
      drain(true);
    },
  };
}
