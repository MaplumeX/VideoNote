import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseSSE = vi.fn();
const mockUseAutoSave = vi.fn();
const mockNavigate = vi.fn();

vi.mock("@/hooks/useSSE", () => ({
  useSSE: (...args: unknown[]) => mockUseSSE(...args),
}));
vi.mock("@/hooks/useNoteAutoSave", () => ({
  useNoteAutoSave: (...args: unknown[]) => mockUseAutoSave(...args),
}));

// A stable `t` is required: NoteDetailPage puts `t` in effect dep arrays,
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
vi.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: "job-1" }),
}));

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
    fetchResult: vi.fn(),
    fetchTaskById: vi.fn(),
    fetchNoteTags: vi.fn(),
    fetchTags: vi.fn(),
    fetchFolderTree: vi.fn(),
    addTagsToNote: vi.fn(),
    removeTagFromNote: vi.fn(),
    moveNoteToFolder: vi.fn(),
    toggleFavorite: vi.fn(),
    updateNoteContent: vi.fn(),
    cancelTask: vi.fn(),
    retryTask: vi.fn(),
  };
});

// Heavy Milkdown editor — replaced with a stub; editor internals are out of scope here.
vi.mock("@/components/NoteEditor", () => ({
  NoteEditor: () => <div data-testid="note-editor" />,
}));
vi.mock("@/components/TableOfContents", () => ({
  TableOfContents: () => null,
}));
vi.mock("@/components/VideoPlayerFloat", () => ({
  VideoPlayerFloat: () => null,
}));

import {
  fetchResult,
  fetchTaskById,
  fetchNoteTags,
  fetchTags,
  fetchFolderTree,
  addTagsToNote,
  removeTagFromNote,
  moveNoteToFolder,
  toggleFavorite,
  ApiError,
} from "@/api/client";
import { NoteDetailPage } from "./NoteDetailPage";

const noteResult = {
  job_id: "job-1",
  markdown: "# Hello\n\nWorld",
  title: "Test Note",
};

const taskItem = {
  job_id: "job-1",
  status: "complete" as const,
  phase: null,
  phase_progress: null,
  message: "",
  created_at: "2024-01-01T12:00:00Z",
  title: "My Video Note",
  video_url: "https://youtu.be/abc",
  file_name: null,
  platform: "youtube",
  language: null,
  source_type: "url",
  folder_id: null,
  is_favorite: true,
  thumbnail_url: "https://example.com/thumb.jpg",
};

const noteTags = [
  { id: "tag-1", user_id: "u1", name: "tag1", color: "#ef4444", created_at: "2024-01-01T00:00:00Z" },
];

const allTags = [
  { ...noteTags[0], note_count: 1 },
  { id: "tag-2", user_id: "u1", name: "suggest-me", color: "#22c55e", created_at: "2024-01-01T00:00:00Z", note_count: 3 },
];

const folderTree = [
  {
    id: "folder-1",
    user_id: "u1",
    name: "Work",
    parent_id: null,
    children: [],
    note_count: 0,
    sort_order: 0,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  },
];

function mockDefaultApiReturnValues() {
  vi.mocked(fetchResult).mockResolvedValue(noteResult);
  vi.mocked(fetchTaskById).mockResolvedValue(taskItem);
  vi.mocked(fetchNoteTags).mockResolvedValue(noteTags);
  vi.mocked(fetchTags).mockResolvedValue(allTags);
  vi.mocked(fetchFolderTree).mockResolvedValue(folderTree);
}

function mockDefaultSSE() {
  mockUseSSE.mockReturnValue({ progress: null, result: null, error: null });
}

function mockDefaultAutoSave(overrides?: { saving?: boolean; saveError?: boolean }) {
  mockUseAutoSave.mockReturnValue({
    handleChange: vi.fn(),
    lastSavedMarkdown: noteResult.markdown,
    reset: vi.fn(),
    saveError: overrides?.saveError ?? false,
    saving: overrides?.saving ?? false,
  });
}

function renderPage() {
  return render(<NoteDetailPage />);
}

async function openNoteInfoPopover() {
  // Two instances exist (≥lg and <lg header variants) — open the first.
  const triggers = await screen.findAllByRole("button", { name: "noteDetail.noteInfo" });
  fireEvent.click(triggers[0]);
  expect(await screen.findByText("noteDetail.folder")).toBeInTheDocument();
}

describe("NoteDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom lacks the layout APIs floating-ui (@base-ui) relies on.
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    mockDefaultApiReturnValues();
    mockDefaultSSE();
    mockDefaultAutoSave();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the header with title, meta info, and back entry (AC1)", async () => {
    renderPage();

    const heading = await screen.findByRole("heading", { level: 1, name: "My Video Note" });
    expect(heading).toBeInTheDocument();

    const backButton = screen.getByRole("button", { name: "noteDetail.backToHistory" });
    expect(backButton).toBeInTheDocument();

    // Meta line shows the platform.
    expect(screen.getByText(/youtube/i)).toBeInTheDocument();
  });

  it("exposes favorite, play, and download actions in the header (AC2)", async () => {
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "My Video Note" });

    // is_favorite=true → the button offers "unfavorite" (visual state).
    expect(screen.getByRole("button", { name: "noteDetail.unfavorite" })).toBeInTheDocument();

    // Platform is youtube with a video_url → play action available.
    expect(screen.getByRole("button", { name: "noteDetail.playVideo" })).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "noteDetail.download" })).toBeInTheDocument();
  });

  it("toggles favorite via the header action", async () => {
    vi.mocked(toggleFavorite).mockResolvedValue(undefined);
    renderPage();

    const favoriteButton = await screen.findByRole("button", { name: "noteDetail.unfavorite" });
    fireEvent.click(favoriteButton);

    await waitFor(() => {
      expect(toggleFavorite).toHaveBeenCalledWith("job-1", { is_favorite: false });
    });
  });

  it("shows the saving status indicator while auto-save is in flight (AC6)", async () => {
    mockDefaultAutoSave({ saving: true });
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "My Video Note" });
    // Rendered in both the ≥lg and <lg header variants.
    expect(screen.getAllByText("noteDetail.saving").length).toBeGreaterThan(0);
  });

  it("shows a save-failure status when auto-save errors (AC6)", async () => {
    mockDefaultAutoSave({ saveError: true });
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "My Video Note" });
    expect(screen.getAllByText("noteDetail.saveFailed").length).toBeGreaterThan(0);
  });

  it("shows the saved status when there are no unsaved changes (AC6)", async () => {
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "My Video Note" });
    expect(screen.getAllByText("noteDetail.saved").length).toBeGreaterThan(0);
  });

  it("adds a tag from the note info popover (AC3)", async () => {
    vi.mocked(addTagsToNote).mockResolvedValue({ tags: noteTags });
    renderPage();

    await openNoteInfoPopover();

    // Existing tag chip is visible.
    expect(screen.getByText("tag1")).toBeInTheDocument();

    // Open the inline tag input and confirm with Enter.
    fireEvent.click(screen.getByText("noteDetail.addTag"));
    const input = await screen.findByPlaceholderText("noteDetail.addTag");
    fireEvent.change(input, { target: { value: "newtag" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(addTagsToNote).toHaveBeenCalledWith("job-1", { tag_names: ["newtag"] });
    });
  });

  it("removes a tag from the note info popover (AC3)", async () => {
    vi.mocked(removeTagFromNote).mockResolvedValue(undefined);
    renderPage();

    await openNoteInfoPopover();

    const removeButton = screen.getByRole("button", { name: "noteDetail.removeTag" });
    fireEvent.click(removeButton);

    await waitFor(() => {
      expect(removeTagFromNote).toHaveBeenCalledWith("job-1", "tag-1");
    });
    await waitFor(() => {
      expect(screen.queryByText("tag1")).not.toBeInTheDocument();
    });
  });

  it("moves the note to a folder from the popover (AC3)", async () => {
    vi.mocked(moveNoteToFolder).mockResolvedValue(undefined);
    renderPage();

    await openNoteInfoPopover();

    fireEvent.click(screen.getByRole("button", { name: "Work" }));

    await waitFor(() => {
      expect(moveNoteToFolder).toHaveBeenCalledWith("job-1", { folder_id: "folder-1" });
    });
  });

  it("closes the note info popover with Escape (AC3)", async () => {
    renderPage();

    await openNoteInfoPopover();

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByText("noteDetail.folder")).not.toBeInTheDocument();
    });
  });

  it("closes the note info popover on outside click (AC3)", async () => {
    renderPage();

    await openNoteInfoPopover();

    // The popover dismisses on an outside (intentional) click.
    fireEvent.click(document.body);

    await waitFor(() => {
      expect(screen.queryByText("noteDetail.folder")).not.toBeInTheDocument();
    });
  });

  it("shows the processing view with progress and cancel when the task is still processing (AC7)", async () => {
    vi.mocked(fetchResult).mockRejectedValue(
      new ApiError("still processing", "TASK_STILL_PROCESSING"),
    );
    renderPage();

    // StepIndicator renders the step labels.
    expect(await screen.findByText("steps.download")).toBeInTheDocument();
    expect(screen.getByText("steps.transcribe")).toBeInTheDocument();
    expect(screen.getByText("steps.generate")).toBeInTheDocument();

    // Video info card context is preserved (title rendered inside the card).
    const cardTitle = await screen.findByText("My Video Note");
    expect(cardTitle.closest(".rounded-lg")).not.toBeNull();

    // Processing (not failed) → cancel available, no retry yet.
    expect(screen.getByRole("button", { name: "processing.cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "processing.retry" })).not.toBeInTheDocument();
  });
  it("keeps video info and shows retry after a processing failure (AC7)", async () => {
    vi.mocked(fetchResult).mockRejectedValue(
      new ApiError("still processing", "TASK_STILL_PROCESSING"),
    );
    mockUseSSE.mockReturnValue({
      progress: {
        status: "failed",
        phase: "transcribe",
        phase_progress: 0.5,
        message: "boom",
        attempt: 1,
        timestamp: "2024-01-01T00:00:00Z",
      },
      result: null,
      error: null,
    });
    renderPage();

    // Failure banner with the SSE message.
    expect(await screen.findByText("boom")).toBeInTheDocument();

    // Video info card context is preserved.
    const cardTitle = await screen.findByText("My Video Note");
    expect(cardTitle.closest(".rounded-lg")).not.toBeNull();

    // Failed state offers retry, not cancel.
    expect(screen.getByRole("button", { name: "processing.retry" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "processing.cancel" })).not.toBeInTheDocument();
  });
});
