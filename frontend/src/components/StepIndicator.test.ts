import { describe, expect, it, vi } from "vitest";
import { getStepStatuses } from "./StepIndicator";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("getStepStatuses", () => {
  it("returns all pending for null stage", () => {
    expect(getStepStatuses(null, 0)).toEqual(["pending", "pending", "pending"]);
  });

  it("returns all pending for pending stage", () => {
    expect(getStepStatuses("pending", 0)).toEqual(["pending", "pending", "pending"]);
  });

  it("maps downloading to step 1 active", () => {
    expect(getStepStatuses("downloading", 0.15)).toEqual(["active", "pending", "pending"]);
  });

  it("maps extracting_subtitles to step 1 active", () => {
    expect(getStepStatuses("extracting_subtitles", 0.1)).toEqual(["active", "pending", "pending"]);
  });

  it("maps transcribing to step 2 active", () => {
    expect(getStepStatuses("transcribing", 0.3)).toEqual(["done", "active", "pending"]);
  });

  it("maps generating_notes to step 3 active", () => {
    expect(getStepStatuses("generating_notes", 0.65)).toEqual(["done", "done", "active"]);
  });

  it("maps complete to all done", () => {
    expect(getStepStatuses("complete", 1.0)).toEqual(["done", "done", "done"]);
  });

  describe("failure localization", () => {
    it("marks only step 1 error when progress < 0.3", () => {
      expect(getStepStatuses("failed", 0.0)).toEqual(["error", "pending", "pending"]);
      expect(getStepStatuses("failed", 0.25)).toEqual(["error", "pending", "pending"]);
    });

    it("marks step 1 done, step 2 error when progress < 0.65", () => {
      expect(getStepStatuses("failed", 0.3)).toEqual(["done", "error", "pending"]);
      expect(getStepStatuses("failed", 0.5)).toEqual(["done", "error", "pending"]);
      expect(getStepStatuses("failed", 0.64)).toEqual(["done", "error", "pending"]);
    });

    it("marks steps 1-2 done, step 3 error when progress >= 0.65", () => {
      expect(getStepStatuses("failed", 0.65)).toEqual(["done", "done", "error"]);
      expect(getStepStatuses("failed", 0.9)).toEqual(["done", "done", "error"]);
    });

    it("localizes cancelled the same as failed", () => {
      expect(getStepStatuses("cancelled", 0.1)).toEqual(["error", "pending", "pending"]);
      expect(getStepStatuses("cancelled", 0.5)).toEqual(["done", "error", "pending"]);
      expect(getStepStatuses("cancelled", 0.7)).toEqual(["done", "done", "error"]);
    });
  });
});