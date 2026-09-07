import { fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  TimestampBadgeView,
  formatSeconds,
  setTimestampContext,
} from "@/components/NoteEditor";
import type { Node as ProseNode } from "@milkdown/prose/model";

function makeNode(attrs: { seconds: number; label?: string }): ProseNode {
  return {
    type: { name: "timestamp-badge" },
    attrs: { label: "", ...attrs },
  } as unknown as ProseNode;
}

describe("TimestampBadgeView", () => {
  const handler = vi.fn();

  afterEach(() => {
    setTimestampContext({ onTimestampClick: undefined, hasVideo: false });
    vi.clearAllMocks();
  });

  beforeEach(() => {
    handler.mockClear();
  });

  it("renders the formatted time as label when no label is given", () => {
    const view = new TimestampBadgeView(makeNode({ seconds: 3661 }));
    expect(view.dom.textContent).toBe("01:01:01");
    view.destroy();
  });

  it("renders the given label when present", () => {
    const view = new TimestampBadgeView(makeNode({ seconds: 90, label: "1:30" }));
    expect(view.dom.textContent).toBe("1:30");
    view.destroy();
  });

  it("invokes the click handler with seconds on mousedown when hasVideo", () => {
    setTimestampContext({ onTimestampClick: handler, hasVideo: true });
    const view = new TimestampBadgeView(makeNode({ seconds: 125 }));
    fireEvent.mouseDown(view.dom);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(125);
    view.destroy();
  });

  it("does not invoke the handler on mousedown when hasVideo is false", () => {
    setTimestampContext({ onTimestampClick: handler, hasVideo: false });
    const view = new TimestampBadgeView(makeNode({ seconds: 125 }));
    fireEvent.mouseDown(view.dom);
    expect(handler).not.toHaveBeenCalled();
    view.destroy();
  });

  it("prevents default and stops propagation on mousedown", () => {
    setTimestampContext({ onTimestampClick: handler, hasVideo: true });
    const view = new TimestampBadgeView(makeNode({ seconds: 10 }));
    const event = new MouseEvent("mousedown", { bubbles: true, cancelable: true });
    const spy = vi.spyOn(event, "preventDefault");
    const stopSpy = vi.spyOn(event, "stopPropagation");
    view.dom.dispatchEvent(event);
    expect(spy).toHaveBeenCalled();
    expect(stopSpy).toHaveBeenCalled();
    view.destroy();
  });

  it("updates style when setTimestampContext changes hasVideo asynchronously", () => {
    // Initially no video: badge should be styled disabled.
    setTimestampContext({ onTimestampClick: handler, hasVideo: false });
    const view = new TimestampBadgeView(makeNode({ seconds: 30 }));
    expect(view.dom.className).toContain("bg-muted");

    // Video info loads asynchronously: badge should restyle as clickable.
    setTimestampContext({ onTimestampClick: handler, hasVideo: true });
    expect(view.dom.className).toContain("bg-accent");
    expect(view.dom.className).toContain("cursor-pointer");

    // And clicking should now invoke the handler.
    fireEvent.mouseDown(view.dom);
    expect(handler).toHaveBeenCalledWith(30);
    view.destroy();
  });

  it("stops restyle after destroy (removed from active views)", () => {
    setTimestampContext({ onTimestampClick: handler, hasVideo: false });
    const view = new TimestampBadgeView(makeNode({ seconds: 30 }));
    const classNameBefore = view.dom.className;
    view.destroy();
    setTimestampContext({ onTimestampClick: handler, hasVideo: true });
    expect(view.dom.className).toBe(classNameBefore);
  });
});

describe("formatSeconds", () => {
  it("formats seconds as HH:MM:SS", () => {
    expect(formatSeconds(0)).toBe("00:00:00");
    expect(formatSeconds(59)).toBe("00:00:59");
    expect(formatSeconds(60)).toBe("00:01:00");
    expect(formatSeconds(3661)).toBe("01:01:01");
  });
});
