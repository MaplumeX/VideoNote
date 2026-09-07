import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock hooks so the page renders purely from a controlled progress stage.
const mockUseSSE = vi.fn();
vi.mock("@/hooks/useSSE", () => ({
  useSSE: (...args: unknown[]) => mockUseSSE(...args),
}));
vi.mock("@/hooks/useVideoUpload", () => ({
  useVideoUpload: () => ({
    uploading: false,
    progress: 0,
    error: null,
    errorCode: null,
    upload: vi.fn(),
  }),
}));

// A stable `t` is required: NewNotePage puts `t` in effect dep arrays,
// so a per-render arrow function would cause an infinite re-render loop.
const { stableT } = vi.hoisted(() => ({
  stableT: (key: string) => key,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: stableT,
    i18n: { resolvedLanguage: "en" },
  }),
  initReactI18next: { type: "3rdParty", init: () => undefined },
}));

const mockNavigate = vi.fn();
const mockSetSearchParams = vi.fn();
vi.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
  useSearchParams: () => [new URLSearchParams("?job=job-1"), mockSetSearchParams],
}));

const mockFetchTaskById = vi.fn();
vi.mock("@/api/client", () => {
  class ApiError extends Error {
    code?: string;
    constructor(message: string, code?: string) {
      super(message);
      this.name = "ApiError";
      this.code = code;
    }
  }
  return {
    ApiError,
    submitUrl: vi.fn(),
    cancelTask: vi.fn(),
    retryTask: vi.fn(),
    fetchTaskById: (...args: unknown[]) => mockFetchTaskById(...args),
  };
});

import { NewNotePage } from "./NewNotePage";

function sseValue(status: string, phase: string | null) {
  return {
    progress: {
      status,
      phase,
      phase_progress: 0,
      message: null,
      attempt: 1,
      timestamp: "",
    },
    result: null,
    error: null,
  };
}

function renderWithStage(status: string, phase: string | null) {
  mockUseSSE.mockReturnValue(sseValue(status, phase));
  const utils = render(<NewNotePage />);
  return utils;
}

// Rerender with a new SSE stage, as the hook would on a progress event.
async function advanceToStage(rerender: (ui: React.ReactElement) => void, status: string, phase: string | null) {
  mockUseSSE.mockReturnValue(sseValue(status, phase));
  rerender(<NewNotePage />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSSE.mockReturnValue(sseValue("pending", null));
  mockSetSearchParams.mockImplementation(() => {});
});

describe("NewNotePage retry button", () => {
  afterEach(cleanup);

  it("shows the Retry button for a failed task", () => {
    renderWithStage("failed", null);
    expect(screen.getByRole("button", { name: "processing.retry" })).toBeInTheDocument();
  });

  it("does not show the Retry button for a cancelled task", () => {
    renderWithStage("cancelled", null);
    expect(screen.queryByRole("button", { name: "processing.retry" })).not.toBeInTheDocument();
  });
});

describe("NewNotePage meta backfill timing", () => {
  afterEach(cleanup);

  it("refetches task meta when the phase advances past fetching", async () => {
    // First backfill: task starts running in fetching phase — meta is still
    // NULL on the backend (update_task_meta runs after fetching completes).
    mockFetchTaskById.mockResolvedValueOnce({
      job_id: "job-1",
      status: "running",
      phase: "fetching",
      phase_progress: 0,
      message: "",
      created_at: "",
      title: null,
      video_url: null,
      file_name: null,
      platform: null,
      language: null,
      source_type: "url",
      folder_id: null,
      is_favorite: false,
      thumbnail_url: null,
    });
    const { rerender } = renderWithStage("running", "fetching");

    // Initial backfill fires immediately
    await waitFor(() => {
      expect(mockFetchTaskById).toHaveBeenCalledTimes(1);
    });
    expect(mockFetchTaskById).toHaveBeenCalledWith("job-1");

    // Phase advances past fetching — video_meta is now persisted on the backend.
    mockFetchTaskById.mockResolvedValueOnce({
      job_id: "job-1",
      status: "running",
      phase: "subtitle",
      phase_progress: 0,
      message: "",
      created_at: "",
      title: "Backfilled Title",
      video_url: "https://example.com/v",
      file_name: null,
      platform: "youtube",
      language: null,
      source_type: "url",
      folder_id: null,
      is_favorite: false,
      thumbnail_url: "http://example.com/thumb.jpg",
    });
    await advanceToStage(rerender, "running", "subtitle");

    await waitFor(() => {
      expect(mockFetchTaskById).toHaveBeenCalledTimes(2);
    });

    // VideoInfoCard now displays the fetched title and thumbnail
    await waitFor(() => {
      expect(screen.getByText("Backfilled Title")).toBeInTheDocument();
    });
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "http://example.com/thumb.jpg");
  });

  it("does not refetch on later phase changes once title and thumbnail are present", async () => {
    // First backfill already returns full meta
    mockFetchTaskById.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      phase: "fetching",
      phase_progress: 0,
      message: "",
      created_at: "",
      title: "Existing Title",
      video_url: null,
      file_name: null,
      platform: "youtube",
      language: null,
      source_type: "url",
      folder_id: null,
      is_favorite: false,
      thumbnail_url: "http://example.com/thumb.jpg",
    });
    const { rerender } = renderWithStage("running", "fetching");

    await waitFor(() => {
      expect(mockFetchTaskById).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByText("Existing Title")).toBeInTheDocument();
    });

    // Phase advances but meta is already populated — no redundant fetches
    await advanceToStage(rerender, "running", "subtitle");
    await advanceToStage(rerender, "running", "transcribe");
    await advanceToStage(rerender, "running", "notegen");
    // Let any (incorrectly scheduled) fetch callbacks flush
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(mockFetchTaskById).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Existing Title")).toBeInTheDocument();
  });

  it("does not trigger the meta refetch loop for upload tasks", async () => {
    // Simulate an upload task opened via URL (?job=...): taskMeta starts null,
    // so the initial backfill fires once and returns the upload task (no
    // title/thumbnail). The merged source_type="upload" must then stop any
    // further refetches as the phase advances.
    mockFetchTaskById.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      phase: "fetching",
      phase_progress: 0,
      message: "",
      created_at: "",
      title: null,
      video_url: null,
      file_name: "video.mp4",
      platform: null,
      language: null,
      source_type: "upload",
      folder_id: null,
      is_favorite: false,
      thumbnail_url: null,
    });
    const { rerender } = renderWithStage("running", "fetching");

    // Initial backfill only
    await waitFor(() => {
      expect(mockFetchTaskById).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByText("videoInfo.unknownFile")).toBeInTheDocument();
      expect(screen.queryByText("video.mp4")).not.toBeInTheDocument();
    });

    // Phase advances — upload tasks never receive video_meta, so no refetches
    await advanceToStage(rerender, "running", "audio");
    await advanceToStage(rerender, "running", "transcribe");
    await advanceToStage(rerender, "running", "notegen");
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(mockFetchTaskById).toHaveBeenCalledTimes(1);
  });
});
