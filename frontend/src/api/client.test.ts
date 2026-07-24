import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import { translateApiError, translateTaskMessage } from "./client";

describe("translateTaskMessage", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("translates stable recovery codes in both supported languages", async () => {
    await i18n.changeLanguage("en");
    expect(translateTaskMessage("TASK_RECOVERY_UNSUPPORTED_URL"))
      .toBe("This task could not be resumed because its video URL is no longer supported.");

    await i18n.changeLanguage("zh-CN");
    expect(translateTaskMessage("TASK_RECOVERY_INPUT_INVALID"))
      .toBe("任务无法恢复：源文件缺失或无效");
  });

  it("preserves legacy free-form task messages", () => {
    expect(translateTaskMessage("Transcription provider failed"))
      .toBe("Transcription provider failed");
  });

  it("translates a recovery code nested in a task-failed API error", async () => {
    await i18n.changeLanguage("zh-CN");
    expect(translateApiError({
      code: "TASK_FAILED",
      params: { message: "TASK_RECOVERY_INPUT_INVALID" },
    })).toBe("任务失败：任务无法恢复：源文件缺失或无效");
  });
});

describe("translateTaskMessage prefix matching", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("translates code with detail suffix", async () => {
    await i18n.changeLanguage("en");
    const result = translateTaskMessage("TRANSCRIPTION_FAILED: rate limit exceeded");
    expect(result).toContain("Audio transcription failed");
    expect(result).toContain("rate limit exceeded");
  });

  it("translates PROVIDER_NOT_CONFIGURED code", async () => {
    await i18n.changeLanguage("en");
    const result = translateTaskMessage("PROVIDER_NOT_CONFIGURED");
    expect(result).toBe("Provider not configured. Please set up your ASR and LLM providers in Settings.");
  });

  it("translates PROVIDER_NOT_CONFIGURED with detail suffix", async () => {
    await i18n.changeLanguage("en");
    const result = translateTaskMessage("PROVIDER_NOT_CONFIGURED: ASR key missing");
    expect(result).toContain("Provider not configured");
    expect(result).toContain("ASR key missing");
  });

  it("falls back to plain code translation when no detail", async () => {
    await i18n.changeLanguage("en");
    expect(translateTaskMessage("TRANSCRIPTION_FAILED")).toBe("Audio transcription failed.");
  });
});
