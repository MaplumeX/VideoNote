import { describe, expect, it } from "vitest";
import type { ProviderPreset } from "@/types";
import { buildConfigForm } from "./SettingsPage";

const presets: ProviderPreset[] = [
  { provider: "openai", models: ["whisper-1"], api_base: "https://api.openai.com/v1" },
  { provider: "deepgram", models: ["nova-2"], api_base: "https://api.deepgram.com/v1" },
];

describe("buildConfigForm", () => {
  it("preselects the first preset when saved is null and presets are non-empty", () => {
    const form = buildConfigForm(null, presets);
    expect(form.provider).toBe("openai");
    expect(form.apiBase).toBe("https://api.openai.com/v1");
    expect(form.model).toBe("");
    expect(form.apiKey).toBe("");
    expect(form.customProviderName).toBe("");
    expect(form.isCustom).toBe(false);
    expect(form.keyMasked).toBe("");
  });

  it("returns an empty form when saved is null and presets are empty", () => {
    const form = buildConfigForm(null, []);
    expect(form).toEqual({
      provider: "",
      model: "",
      apiKey: "",
      apiBase: "",
      customProviderName: "",
      isCustom: false,
      keyMasked: "",
    });
  });

  it("echoes back a saved preset provider config unchanged", () => {
    const form = buildConfigForm(
      {
        provider: "deepgram",
        model: "nova-2",
        api_key_masked: "sk-***1234",
        api_base: "https://api.deepgram.com/v1",
      },
      presets
    );
    expect(form).toEqual({
      provider: "deepgram",
      model: "nova-2",
      apiKey: "",
      apiBase: "https://api.deepgram.com/v1",
      customProviderName: "",
      isCustom: false,
      keyMasked: "sk-***1234",
    });
  });

  it("falls back to custom provider when saved provider is not in presets", () => {
    const form = buildConfigForm(
      {
        provider: "my-own-asr",
        model: "m1",
        api_key_masked: "abcd",
        api_base: "https://example.com/v1",
      },
      presets
    );
    expect(form).toEqual({
      provider: "custom",
      model: "m1",
      apiKey: "",
      apiBase: "https://example.com/v1",
      customProviderName: "my-own-asr",
      isCustom: true,
      keyMasked: "abcd",
    });
  });
});
