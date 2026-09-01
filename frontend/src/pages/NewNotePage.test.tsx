import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: "en" },
  }),
  initReactI18next: { type: "3rdParty", init: () => undefined },
}));
vi.mock("react-router", () => ({
  useNavigate: () => vi.fn(),
  useSearchParams: () => [new URLSearchParams("?job=job-1"), vi.fn()],
}));

import { NewNotePage } from "./NewNotePage";

function renderWithStage(stage: string) {
  mockUseSSE.mockReturnValue({ progress: { stage, progress: 0.1, message: null }, result: null, error: null });
  render(<NewNotePage />);
}

describe("NewNotePage retry button", () => {
  afterEach(cleanup);

  it("shows the Retry button for a failed task", () => {
    renderWithStage("failed");
    expect(screen.getByRole("button", { name: "processing.retry" })).toBeInTheDocument();
  });

  it("does not show the Retry button for a cancelled task", () => {
    renderWithStage("cancelled");
    expect(screen.queryByRole("button", { name: "processing.retry" })).not.toBeInTheDocument();
  });
});
