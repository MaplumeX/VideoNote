import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authFetch } from "../auth/api";
import { fetchResult, fetchTaskById } from "../api/client";
import { useSSE } from "./useSSE";

const { translate } = vi.hoisted(() => ({
  translate: (key: string) => key,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate }),
}));

vi.mock("../auth/api", () => ({
  authFetch: vi.fn(),
}));

vi.mock("../api/client", () => ({
  fetchResult: vi.fn(),
  fetchTaskById: vi.fn(),
  getProgressUrl: (jobId: string) => `/api/tasks/${jobId}/progress`,
  translateTaskMessage: (message: string) => (
    message === "TASK_RECOVERY_INPUT_INVALID" ? "translated recovery error" : message
  ),
}));

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  }), { status: 200 });
}

describe("useSSE", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("recovers a completed task after the progress stream disconnects", async () => {
    vi.mocked(authFetch).mockResolvedValue(streamResponse([]));
    vi.mocked(fetchTaskById).mockResolvedValue({
      job_id: "job-1",
      stage: "complete",
      progress: 1,
      message: "done",
      created_at: "",
      title: null,
      video_url: null,
      file_name: null,
      platform: null,
      language: null,
      source_type: null,
      folder_id: null,
      is_favorite: false,
      thumbnail_url: null,
    });
    vi.mocked(fetchResult).mockResolvedValue({
      job_id: "job-1",
      markdown: "# recovered",
      title: null,
    });

    const { result } = renderHook(() => useSSE("job-1"));

    await waitFor(() => {
      expect(result.current.result).toBe("# recovered");
    });
    expect(result.current.error).toBeNull();
    expect(fetchTaskById).toHaveBeenCalledWith("job-1");
    expect(fetchResult).toHaveBeenCalledWith("job-1");
  });

  it("reconnects a non-terminal task and parses the next stream", async () => {
    vi.mocked(authFetch)
      .mockResolvedValueOnce(streamResponse([]))
      .mockResolvedValueOnce(streamResponse([
        "event: progress\r\n",
        "data: {\"stage\":\"complete\",\"progress\":1,\"message\":\"done\"}\r\n\r\n",
        "event: complete\r\n",
        "data: {\"markdown\":\"# streamed\"}\r\n\r\n",
      ]));
    vi.mocked(fetchTaskById).mockResolvedValue({
      job_id: "job-2",
      stage: "transcribing",
      progress: 0.5,
      message: "working",
      created_at: "",
      title: null,
      video_url: null,
      file_name: null,
      platform: null,
      language: null,
      source_type: null,
      folder_id: null,
      is_favorite: false,
      thumbnail_url: null,
    });

    const { result } = renderHook(() => useSSE("job-2"));

    await waitFor(() => {
      expect(result.current.result).toBe("# streamed");
    });
    expect(authFetch).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
  });

  it("aborts the active stream when the hook unmounts", () => {
    let requestSignal: AbortSignal | undefined;
    vi.mocked(authFetch).mockImplementation(async (_url, options) => {
      requestSignal = options?.signal ?? undefined;
      return new Response(new ReadableStream());
    });

    const { unmount } = renderHook(() => useSSE("job-3"));
    unmount();

    expect(requestSignal?.aborted).toBe(true);
  });

  it("translates a stable recovery failure code from the stream", async () => {
    vi.mocked(authFetch).mockResolvedValue(streamResponse([
      "event: progress\n",
      "data: {\"stage\":\"failed\",\"progress\":0,\"message\":\"TASK_RECOVERY_INPUT_INVALID\"}\n\n",
    ]));

    const { result } = renderHook(() => useSSE("job-4"));

    await waitFor(() => {
      expect(result.current.error).toBe("translated recovery error");
    });
    expect(result.current.progress?.message).toBe("translated recovery error");
  });
});

describe("useSSE reconnect quota", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("resets reconnectAttempt after first event received, then recovers on normal close", async () => {
    // Simulate: stream opens → first progress event received (reconnect resets) →
    // stream closes normally (server timeout) → fetchTaskById returns processing →
    // reconnects without consuming quota → second stream sends complete.
    vi.mocked(authFetch)
      .mockResolvedValueOnce(streamResponse([
        "event: progress\r\n",
        "data: {\"stage\":\"transcribing\",\"progress\":0.3,\"message\":\"working\"}\r\n\r\n",
      ]))
      .mockResolvedValueOnce(streamResponse([
        "event: complete\r\n",
        "data: {\"markdown\":\"# done\"}\r\n\r\n",
      ]));
    vi.mocked(fetchTaskById).mockResolvedValue({
      job_id: "job-rc",
      stage: "transcribing",
      progress: 0.3,
      message: "working",
      created_at: "",
      title: null,
      video_url: null,
      file_name: null,
      platform: null,
      language: null,
      source_type: null,
      folder_id: null,
      is_favorite: false,
      thumbnail_url: null,
    });

    const { result } = renderHook(() => useSSE("job-rc"));

    await waitFor(() => {
      expect(result.current.result).toBe("# done");
    });
    expect(result.current.error).toBeNull();
    // First stream received an event (1 call) + second stream (1 call) = 2 total
    expect(authFetch).toHaveBeenCalledTimes(2);
  });

  it("increments reconnectAttempt on true network failure before first event", async () => {
    // Simulate: connection drops immediately (no events) — fetchTaskById returns
    // processing — should consume a reconnect slot (exponential backoff).
    // Then second stream succeeds.
    vi.mocked(authFetch)
      .mockResolvedValueOnce(streamResponse([])) // empty stream, no events
      .mockResolvedValueOnce(streamResponse([
        "event: complete\r\n",
        "data: {\"markdown\":\"# recovered2\"}\r\n\r\n",
      ]));
    vi.mocked(fetchTaskById).mockResolvedValue({
      job_id: "job-nf",
      stage: "transcribing",
      progress: 0.3,
      message: "working",
      created_at: "",
      title: null,
      video_url: null,
      file_name: null,
      platform: null,
      language: null,
      source_type: null,
      folder_id: null,
      is_favorite: false,
      thumbnail_url: null,
    });

    const { result } = renderHook(() => useSSE("job-nf"));

    await waitFor(() => {
      expect(result.current.result).toBe("# recovered2");
    });
    expect(result.current.error).toBeNull();
    expect(authFetch).toHaveBeenCalledTimes(2);
  });
});
