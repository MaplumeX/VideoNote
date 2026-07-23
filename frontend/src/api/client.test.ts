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
