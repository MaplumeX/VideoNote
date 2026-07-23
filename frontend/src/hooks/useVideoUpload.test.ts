import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearAuth, getAccessToken } from "../auth/token";
import { useVideoUpload } from "./useVideoUpload";

class FakeXMLHttpRequest {
  static latest: FakeXMLHttpRequest | null = null;

  readonly upload: { onprogress: ((event: ProgressEvent) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void | Promise<void>) | null = null;
  onerror: (() => void) | null = null;
  status = 0;
  responseText = "";
  body: Document | XMLHttpRequestBodyInit | null = null;
  headers = new Map<string, string>();

  constructor() {
    FakeXMLHttpRequest.latest = this;
  }

  open(): void {}

  setRequestHeader(name: string, value: string): void {
    this.headers.set(name, value);
  }

  send(body?: Document | XMLHttpRequestBodyInit | null): void {
    this.body = body ?? null;
  }

  async respond(status: number, body: object): Promise<void> {
    this.status = status;
    this.responseText = JSON.stringify(body);
    await this.onload?.();
  }
}

describe("useVideoUpload", () => {
  beforeEach(() => {
    clearAuth();
    FakeXMLHttpRequest.latest = null;
    vi.restoreAllMocks();
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
  });

  it("sends language as a multipart form field", async () => {
    const { result } = renderHook(() => useVideoUpload());
    let uploadPromise = Promise.resolve("");

    act(() => {
      uploadPromise = result.current.upload(
        new File(["video"], "demo.mp4", { type: "video/mp4" }),
        "zh-CN",
        "token",
      );
    });

    const xhr = FakeXMLHttpRequest.latest;
    expect(xhr).not.toBeNull();
    const form = xhr?.body;
    expect(form).toBeInstanceOf(FormData);
    expect((form as FormData).get("language")).toBe("zh-CN");
    expect(xhr?.headers.get("Authorization")).toBe("Bearer token");

    await act(async () => {
      await xhr?.respond(200, { job_id: "job-1" });
      await expect(uploadPromise).resolves.toBe("job-1");
    });
  });

  it("refreshes an expired session but requires an explicit re-upload", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => (
      new Response(JSON.stringify({ access_token: "fresh" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )));
    const { result } = renderHook(() => useVideoUpload());
    let uploadPromise = Promise.resolve("");

    act(() => {
      uploadPromise = result.current.upload(
        new File(["video"], "demo.mp4", { type: "video/mp4" }),
        "en",
        "expired",
      );
    });

    await act(async () => {
      await FakeXMLHttpRequest.latest?.respond(401, {});
      await expect(uploadPromise).resolves.toBe("");
    });

    expect(getAccessToken()).toBe("fresh");
    expect(result.current.error).not.toBeNull();
  });
});
