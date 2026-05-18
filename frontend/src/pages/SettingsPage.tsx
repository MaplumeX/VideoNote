import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { fetchProviders, fetchSettings, saveSettings } from "@/api/client";
import type {
  ProviderPreset,
  ProvidersResponse,
  SettingsResponse,
  ProviderConfig,
} from "@/types";
import { Mic, Brain, Save, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

interface ConfigFormState {
  provider: string;
  model: string;
  apiKey: string;
  apiBase: string;
  customProviderName: string;
  isCustom: boolean;
  keyMasked: string;
}

const emptyConfig: ConfigFormState = {
  provider: "",
  model: "",
  apiKey: "",
  apiBase: "",
  customProviderName: "",
  isCustom: false,
  keyMasked: "",
};

function buildConfigForm(
  saved: SettingsResponse["asr"] | SettingsResponse["llm"],
  presets: ProviderPreset[]
): ConfigFormState {
  if (!saved) return { ...emptyConfig };

  const matched = presets.find((p) => p.provider === saved.provider);
  const isCustom = !matched;

  return {
    provider: isCustom ? "custom" : saved.provider,
    model: saved.model,
    apiKey: "",
    apiBase: saved.api_base,
    customProviderName: isCustom ? saved.provider : "",
    isCustom,
    keyMasked: saved.api_key_masked,
  };
}

interface ProviderConfigSectionProps {
  title: string;
  icon: React.ReactNode;
  presets: ProviderPreset[];
  form: ConfigFormState;
  onChange: (form: ConfigFormState) => void;
}

function ProviderConfigSection({
  title,
  icon,
  presets,
  form,
  onChange,
}: ProviderConfigSectionProps) {
  const { t } = useTranslation();

  const selectedPreset = presets.find((p) => p.provider === form.provider);
  const models = selectedPreset?.models ?? [];

  const handleProviderChange = (value: string) => {
    if (value === "custom") {
      onChange({
        ...emptyConfig,
        isCustom: true,
        provider: "custom",
        keyMasked: form.keyMasked,
      });
    } else {
      const preset = presets.find((p) => p.provider === value);
      onChange({
        ...emptyConfig,
        provider: value,
        apiBase: preset?.api_base ?? "",
        model: preset?.models[0] ?? "",
        keyMasked: form.keyMasked,
      });
    }
  };

  const inputClass =
    "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 transition-colors";
  const labelClass = "block text-sm font-medium mb-1.5";
  const selectClass =
    "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/50 transition-colors appearance-none bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2012%2012%22%3E%3Cpath%20d%3D%22M3%204.5L6%208l3-3.5%22%20fill%3D%22none%22%20stroke%3D%22%23666%22%20stroke-width%3D%221.5%22%2F%3E%3C%2Fsvg%3E')] bg-[length:12px] bg-[right_12px_center] bg-no-repeat pr-8";

  return (
    <div className="rounded-lg border border-border p-6 space-y-4">
      <div className="flex items-center gap-2">
        {icon}
        <h3 className="text-base font-semibold">{title}</h3>
      </div>

      {/* Provider select */}
      <div>
        <label className={labelClass}>{t("settings.provider")}</label>
        <select
          value={form.provider}
          onChange={(e) => handleProviderChange(e.target.value)}
          className={selectClass}
        >
          <option value="">{t("settings.provider")}</option>
          {presets.map((p) => (
            <option key={p.provider} value={p.provider}>
              {p.provider}
            </option>
          ))}
          <option value="custom">{t("settings.custom")}</option>
        </select>
      </div>

      {/* Custom provider name */}
      {form.isCustom && (
        <div>
          <label className={labelClass}>{t("settings.customProvider")}</label>
          <input
            type="text"
            value={form.customProviderName}
            onChange={(e) => onChange({ ...form, customProviderName: e.target.value })}
            className={inputClass}
            placeholder={t("settings.customProvider")}
          />
        </div>
      )}

      {/* Model */}
      {!form.isCustom && models.length > 0 ? (
        <div>
          <label className={labelClass}>{t("settings.model")}</label>
          <select
            value={form.model}
            onChange={(e) => onChange({ ...form, model: e.target.value })}
            className={selectClass}
          >
            <option value="">{t("settings.model")}</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <div>
          <label className={labelClass}>{t("settings.model")}</label>
          <input
            type="text"
            value={form.model}
            onChange={(e) => onChange({ ...form, model: e.target.value })}
            className={inputClass}
            placeholder={t("settings.model")}
          />
        </div>
      )}

      {/* API Base */}
      <div>
        <label className={labelClass}>{t("settings.apiBase")}</label>
        <input
          type="url"
          value={form.apiBase}
          onChange={(e) => onChange({ ...form, apiBase: e.target.value })}
          className={inputClass}
          placeholder="https://api.example.com/v1"
        />
      </div>

      {/* API Key */}
      <div>
        <label className={labelClass}>{t("settings.apiKey")}</label>
        <input
          type="password"
          value={form.apiKey}
          onChange={(e) => onChange({ ...form, apiKey: e.target.value })}
          className={inputClass}
          placeholder={
            form.keyMasked
              ? t("settings.keyMasked", { last4: form.keyMasked.slice(-4) })
              : t("settings.keyPlaceholder")
          }
        />
      </div>
    </div>
  );
}

function buildPayload(form: ConfigFormState): ProviderConfig | null {
  const provider = form.isCustom ? form.customProviderName : form.provider;
  if (!provider || !form.model || !form.apiBase) return null;

  return {
    provider,
    model: form.model,
    api_key: form.apiKey,
    api_base: form.apiBase,
  };
}

export function SettingsPage() {
  const { t } = useTranslation();

  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [asrForm, setAsrForm] = useState<ConfigFormState>({ ...emptyConfig });
  const [llmForm, setLlmForm] = useState<ConfigFormState>({ ...emptyConfig });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [providersRes, settingsRes] = await Promise.all([
        fetchProviders(),
        fetchSettings(),
      ]);
      setProviders(providersRes);
      setAsrForm(buildConfigForm(settingsRes.asr, providersRes.asr));
      setLlmForm(buildConfigForm(settingsRes.llm, providersRes.llm));
    } catch {
      setMessage({ type: "error", text: t("settings.saveFailed") });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleSave = async () => {
    setMessage(null);
    setSaving(true);

    const asr = buildPayload(asrForm);
    const llm = buildPayload(llmForm);

    try {
      await saveSettings({
        asr: asr ?? null,
        llm: llm ?? null,
      });

      // Reload to refresh masked keys
      await loadData();
      setMessage({ type: "success", text: t("settings.saved") });
    } catch {
      setMessage({ type: "error", text: t("settings.saveFailed") });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">{t("history.loading")}</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Settings size={20} />
        <h2 className="text-lg font-bold">{t("settings.title")}</h2>
      </div>

      {message && (
        <div
          className={cn(
            "rounded-lg border px-4 py-3 text-sm",
            message.type === "success"
              ? "bg-green-500/10 border-green-500/20 text-green-600"
              : "bg-destructive/10 border-destructive/20 text-destructive"
          )}
        >
          {message.text}
        </div>
      )}

      <ProviderConfigSection
        title={t("settings.asrConfig")}
        icon={<Mic size={18} className="text-muted-foreground" />}
        presets={providers?.asr ?? []}
        form={asrForm}
        onChange={setAsrForm}
      />

      <ProviderConfigSection
        title={t("settings.llmConfig")}
        icon={<Brain size={18} className="text-muted-foreground" />}
        presets={providers?.llm ?? []}
        form={llmForm}
        onChange={setLlmForm}
      />

      <div className="flex justify-end">
        <button
          onClick={() => void handleSave()}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save size={16} />
          {saving ? "..." : t("settings.save")}
        </button>
      </div>
    </div>
  );
}
