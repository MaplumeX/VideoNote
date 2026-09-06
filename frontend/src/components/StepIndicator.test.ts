import { describe, expect, it, vi } from "vitest";
import { getStepStatuses } from "./StepIndicator";
import { synthesizeProgress, pathForSource } from "@/lib/phaseProgress";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("getStepStatuses", () => {
  it("returns all pending for null status", () => {
    expect(getStepStatuses(null, null)).toEqual(["pending", "pending", "pending"]);
  });

  it("returns all pending for pending status", () => {
    expect(getStepStatuses("pending", null)).toEqual(["pending", "pending", "pending"]);
  });

  it("returns all pending for running with null phase", () => {
    expect(getStepStatuses("running", null)).toEqual(["pending", "pending", "pending"]);
  });

  it("maps fetching to step 1 active", () => {
    expect(getStepStatuses("running", "fetching")).toEqual(["active", "pending", "pending"]);
  });

  it("maps subtitle to step 1 active", () => {
    expect(getStepStatuses("running", "subtitle")).toEqual(["active", "pending", "pending"]);
  });

  it("maps audio to step 1 active on the URL path", () => {
    expect(getStepStatuses("running", "audio")).toEqual(["active", "pending", "pending"]);
  });

  it("maps audio to step 1 active on the upload path", () => {
    expect(getStepStatuses("running", "audio")).toEqual(["active", "pending", "pending"]);
  });

  it("maps transcribe to step 2 active", () => {
    expect(getStepStatuses("running", "transcribe")).toEqual(["done", "active", "pending"]);
  });

  it("maps notegen to step 3 active", () => {
    expect(getStepStatuses("running", "notegen")).toEqual(["done", "done", "active"]);
  });

  it("maps complete to all done", () => {
    expect(getStepStatuses("complete", null)).toEqual(["done", "done", "done"]);
  });

  describe("failure localization", () => {
    it("marks only step 1 error when failed in fetching", () => {
      expect(getStepStatuses("failed", null, "fetching")).toEqual(["error", "pending", "pending"]);
    });

    it("marks only step 1 error when failed in subtitle", () => {
      expect(getStepStatuses("failed", null, "subtitle")).toEqual(["error", "pending", "pending"]);
    });

    it("marks only step 1 error when failed in audio", () => {
      expect(getStepStatuses("failed", null, "audio")).toEqual(["error", "pending", "pending"]);
    });

    it("marks step 1 done, step 2 error when failed in transcribe", () => {
      expect(getStepStatuses("failed", null, "transcribe")).toEqual(["done", "error", "pending"]);
    });

    it("marks steps 1-2 done, step 3 error when failed in notegen", () => {
      expect(getStepStatuses("failed", null, "notegen")).toEqual(["done", "done", "error"]);
    });

    it("localizes cancelled the same as failed", () => {
      expect(getStepStatuses("cancelled", null, "audio")).toEqual(["error", "pending", "pending"]);
      expect(getStepStatuses("cancelled", null, "transcribe")).toEqual(["done", "error", "pending"]);
      expect(getStepStatuses("cancelled", null, "notegen")).toEqual(["done", "done", "error"]);
    });

    it("marks the whole row error when terminal without phase info (legacy rows)", () => {
      expect(getStepStatuses("failed", null, null)).toEqual(["error", "error", "error"]);
      expect(getStepStatuses("cancelled", null, null)).toEqual(["error", "error", "error"]);
    });

    it("localizes upload-path failures (audio is step 1)", () => {
      expect(getStepStatuses("failed", null, "audio")).toEqual(["error", "pending", "pending"]);
    });
  });
});

describe("synthesizeProgress", () => {
  it("returns 0 for a null phase", () => {
    expect(synthesizeProgress(null, 0.5, pathForSource("url"))).toBe(0);
  });

  it("computes URL-path progress for fetching", () => {
    // (0 + 0.5) / 5 = 0.1
    expect(synthesizeProgress("fetching", 0.5, pathForSource("url"))).toBeCloseTo(0.1);
  });

  it("computes URL-path progress for transcribe", () => {
    // (3 + 0.5) / 5 = 0.7
    expect(synthesizeProgress("transcribe", 0.5, pathForSource("url"))).toBeCloseTo(0.7);
  });

  it("computes upload-path progress for transcribe", () => {
    // (1 + 0.5) / 3 = 0.5
    expect(synthesizeProgress("transcribe", 0.5, pathForSource("upload"))).toBeCloseTo(0.5);
  });

  it("subtitle hit naturally lands in the notegen segment when reached", () => {
    // subtitle hit skips audio+transcribe; once notegen runs the synthesized
    // value is (4 + 0) / 5 = 0.8 — no special-casing needed.
    expect(synthesizeProgress("notegen", 0, pathForSource("url"))).toBeCloseTo(0.8);
  });

  it("clamps phase_progress to [0, 1]", () => {
    expect(synthesizeProgress("fetching", 2, pathForSource("url"))).toBeCloseTo(1 / 5);
    expect(synthesizeProgress("fetching", -1, pathForSource("url"))).toBe(0);
  });

  it("returns 0 for a phase not on the path", () => {
    expect(synthesizeProgress("fetching", 0.5, pathForSource("upload"))).toBe(0);
  });
});
