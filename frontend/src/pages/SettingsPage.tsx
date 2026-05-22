import { useEffect, useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { fetchProviders, fetchSettings, saveSettings, fetchModels, fetchCookies, saveCookie, deleteCookie } from "@/api/client";
import type {
  ProviderPreset,
  ProvidersResponse,
  SettingsResponse,
  ProviderConfig,
  CookieInfo,
} from "@/types";
import { Mic, Brain, Save, Settings, Globe, Cookie, Trash2, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { SUPPORTED_LANGS } from "@/i18n";
import { useConfirm } from "@/hooks/useConfirm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Combobox } from "@/components/ui/combobox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDropzone } from "react-dropzone";

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

const labelClass = "block text-sm font-medium mb-1.5";

interface ProviderConfigSectionProps {
  title: string;
  icon: React.ReactNode;
  category: "asr" | "llm";
  presets: ProviderPreset[];
  form: ConfigFormState;
  onChange: (form: ConfigFormState) => void;
}

function ProviderConfigSection({
  title,
  icon,
  category,
  presets,
  form,
  onChange,
}: ProviderConfigSectionProps) {
  const { t } = useTranslation();

  const [dynamicModels, setDynamicModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const prevFetchRef = useRef({ apiKey: "", apiBase: "" });

  const selectedPreset = presets.find((p) => p.provider === form.provider);
  const presetModels = selectedPreset?.models ?? [];

  // Determine effective model list: dynamic if fetched, otherwise preset fallback
  const modelOptions = dynamicModels.length > 0 ? dynamicModels : presetModels;

  const fetchDynamicModels = useCallback(
    async (apiKey: string, apiBase: string) => {
      if (!apiKey || !apiBase) {
        setDynamicModels([]);
        return;
      }
      // Avoid duplicate fetches for the same key+base
      const key = `${apiKey}:${apiBase}`;
      if (prevFetchRef.current.apiKey + ":" + prevFetchRef.current.apiBase === key) return;
      prevFetchRef.current = { apiKey, apiBase };

      setModelsLoading(true);
      try {
        const res = await fetchModels(apiKey, apiBase, category);
        if (res.error) {
          setDynamicModels([]);
        } else {
          setDynamicModels(res.models.map((m) => m.id).sort());
        }
      } catch {
        setDynamicModels([]);
      } finally {
        setModelsLoading(false);
      }
    },
    [category]
  );

  // Auto-fetch models when provider + api key are both available
  useEffect(() => {
    // For preset provider: need apiKey and apiBase
    // For custom provider: need apiKey and apiBase
    const apiKey = form.apiKey;
    const apiBase = form.apiBase;
    if (apiKey && apiBase) {
      void fetchDynamicModels(apiKey, apiBase);
    } else {
      setDynamicModels([]);
      prevFetchRef.current = { apiKey: "", apiBase: "" };
    }
  }, [form.apiKey, form.apiBase, fetchDynamicModels]);

  const handleProviderChange = (value: string | null) => {
    if (!value) return;
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
        model: "",
        keyMasked: form.keyMasked,
      });
    }
    // Reset dynamic models when provider changes
    setDynamicModels([]);
    prevFetchRef.current = { apiKey: "", apiBase: "" };
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {icon}
          <CardTitle>{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Provider select */}
        <div>
          <label className={labelClass}>{t("settings.provider")}</label>
          <Select value={form.provider} onValueChange={handleProviderChange}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("settings.provider")} />
            </SelectTrigger>
            <SelectContent align="start" alignItemWithTrigger={false}>
              {presets.map((p) => (
                <SelectItem key={p.provider} value={p.provider}>
                  {p.provider}
                </SelectItem>
              ))}
              <SelectItem value="custom">{t("settings.custom")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Custom provider name */}
        {form.isCustom && (
          <div>
            <label className={labelClass}>{t("settings.customProvider")}</label>
            <Input
              type="text"
              value={form.customProviderName}
              onChange={(e) => onChange({ ...form, customProviderName: e.target.value })}
              placeholder={t("settings.customProvider")}
            />
          </div>
        )}

        {/* Model - Combobox for both preset and custom */}
        <div>
          <label className={labelClass}>{t("settings.model")}</label>
          <Combobox
            value={form.model}
            onChange={(v) => onChange({ ...form, model: v })}
            options={modelOptions}
            placeholder={t("settings.model")}
            loading={modelsLoading}
            loadingText={t("settings.loadingModels")}
            emptyText={t("settings.noModels")}
          />
        </div>

        {/* API Base */}
        <div>
          <label className={labelClass}>{t("settings.apiBase")}</label>
          <Input
            type="url"
            value={form.apiBase}
            onChange={(e) => onChange({ ...form, apiBase: e.target.value })}
            placeholder="https://api.example.com/v1"
          />
        </div>

        {/* API Key */}
        <div>
          <label className={labelClass}>{t("settings.apiKey")}</label>
          <Input
            type="password"
            value={form.apiKey}
            onChange={(e) => onChange({ ...form, apiKey: e.target.value })}
            placeholder={
              form.keyMasked
                ? t("settings.keyMasked", { last4: form.keyMasked.slice(-4) })
                : t("settings.keyPlaceholder")
            }
          />
        </div>
      </CardContent>
    </Card>
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

const LANG_LABELS: Record<string, string> = {
  en: "English",
  "zh-CN": "中文",
};

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  bilibili: "Bilibili",
};

interface CookiePlatformSectionProps {
  platform: string;
  cookieInfo: CookieInfo | undefined;
  onUpload: (platform: string, file: File) => void;
  onPaste: (platform: string, text: string) => void;
  onDelete: (platform: string) => void;
  loading: boolean;
}

function CookiePlatformSection({
  platform,
  cookieInfo,
  onUpload,
  onPaste,
  onDelete,
  loading,
}: CookiePlatformSectionProps) {
  const { t } = useTranslation();
  const [pasteText, setPasteText] = useState("");
  const [pasteMode, setPasteMode] = useState(false);

  const platformLabel = PLATFORM_LABELS[platform] ?? platform;

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) {
        onUpload(platform, acceptedFiles[0]);
      }
    },
    [onUpload, platform],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "text/plain": [".txt"] },
    maxFiles: 1,
    disabled: loading,
  });

  const handlePasteSave = () => {
    if (pasteText.trim()) {
      onPaste(platform, pasteText.trim());
      setPasteText("");
      setPasteMode(false);
    }
  };

  const hasCookie = cookieInfo?.has_cookie ?? false;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{platformLabel}</span>
        <span
          className={cn(
            "text-xs px-2 py-0.5 rounded-full",
            hasCookie
              ? "bg-green-500/10 text-green-600 dark:text-green-400"
              : "bg-muted text-muted-foreground",
          )}
        >
          {hasCookie ? t("settings.cookieSet") : t("settings.cookieNotSet")}
        </span>
      </div>

      <div className="flex gap-2">
        <div {...getRootProps()} className="flex-1">
          <input {...getInputProps()} />
          <Button
            variant="outline"
            size="sm"
            className={cn("w-full gap-1.5", isDragActive && "border-primary")}
            disabled={loading}
            onClick={(e) => { e.preventDefault(); getRootProps().onClick?.(e); }}
          >
            <Upload size={14} />
            {t("settings.cookieUpload")}
          </Button>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={loading}
          onClick={() => setPasteMode(!pasteMode)}
        >
          {t("settings.cookiePaste")}
        </Button>
        {hasCookie && (
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-destructive hover:text-destructive"
            disabled={loading}
            onClick={() => onDelete(platform)}
          >
            <Trash2 size={14} />
            {t("settings.cookieDelete")}
          </Button>
        )}
      </div>

      {pasteMode && (
        <div className="space-y-2">
          <textarea
            className="w-full rounded-md border bg-background px-3 py-2 text-sm min-h-[80px] resize-y focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder={t("settings.cookiePastePlaceholder")}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            disabled={loading}
          />
          <Button
            size="sm"
            className="gap-1.5"
            disabled={loading || !pasteText.trim()}
            onClick={handlePasteSave}
          >
            {t("settings.cookieSave")}
          </Button>
        </div>
      )}
    </div>
  );
}

function CookieCard() {
  const { t } = useTranslation();
  const { confirm } = useConfirm();
  const [cookies, setCookies] = useState<CookieInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadCookies = useCallback(async () => {
    try {
      const data = await fetchCookies();
      setCookies(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCookies();
  }, [loadCookies]);

  const handleUpload = async (platform: string, file: File) => {
    setLoading(true);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await saveCookie(platform, formData);
      setMessage({ type: "success", text: t("settings.cookieSaved") });
      await loadCookies();
    } catch {
      setMessage({ type: "error", text: t("settings.cookieSaveFailed") });
    } finally {
      setLoading(false);
    }
  };

  const handlePaste = async (platform: string, text: string) => {
    setLoading(true);
    setMessage(null);
    try {
      await saveCookie(platform, { cookie_text: text });
      setMessage({ type: "success", text: t("settings.cookieSaved") });
      await loadCookies();
    } catch {
      setMessage({ type: "error", text: t("settings.cookieSaveFailed") });
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (platform: string) => {
    const platformLabel = PLATFORM_LABELS[platform] ?? platform;
    const ok = await confirm({
      title: t("settings.cookieDelete"),
      description: t("settings.cookieDeleteConfirm", { platform: platformLabel }),
      destructive: true,
    });
    if (!ok) return;
    setLoading(true);
    setMessage(null);
    try {
      await deleteCookie(platform);
      setMessage({ type: "success", text: t("settings.cookieDeleted") });
      await loadCookies();
    } catch {
      setMessage({ type: "error", text: t("settings.cookieDeleteFailed") });
    } finally {
      setLoading(false);
    }
  };

  const getCookieInfo = (platform: string) => cookies.find((c) => c.platform === platform);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Cookie size={18} className="text-muted-foreground" />
          <CardTitle>{t("settings.cookieTitle")}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <p className="text-sm text-muted-foreground">{t("settings.cookieDesc")}</p>

        {message && (
          <div
            className={cn(
              "rounded-lg border px-4 py-3 text-sm",
              message.type === "success"
                ? "bg-green-500/10 border-green-500/20 text-green-600 dark:text-green-400"
                : "bg-destructive/10 border-destructive/20 text-destructive",
            )}
          >
            {message.text}
          </div>
        )}

        <CookiePlatformSection
          platform="youtube"
          cookieInfo={getCookieInfo("youtube")}
          onUpload={handleUpload}
          onPaste={handlePaste}
          onDelete={handleDelete}
          loading={loading}
        />

        <CookiePlatformSection
          platform="bilibili"
          cookieInfo={getCookieInfo("bilibili")}
          onUpload={handleUpload}
          onPaste={handlePaste}
          onDelete={handleDelete}
          loading={loading}
        />

        <p className="text-xs text-muted-foreground">{t("settings.cookieFileHint")}</p>
      </CardContent>
    </Card>
  );
}

export function SettingsPage() {
  const { t, i18n } = useTranslation();

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
              ? "bg-green-500/10 border-green-500/20 text-green-600 dark:text-green-400"
              : "bg-destructive/10 border-destructive/20 text-destructive"
          )}
        >
          {message.text}
        </div>
      )}

      {/* Language */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe size={18} className="text-muted-foreground" />
            <CardTitle>{t("settings.language")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Select
            value={i18n.resolvedLanguage ?? "en"}
            onValueChange={(v) => { if (v) void i18n.changeLanguage(v); }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("settings.language")}>
                {LANG_LABELS[i18n.resolvedLanguage ?? "en"] ?? i18n.resolvedLanguage}
              </SelectValue>
            </SelectTrigger>
            <SelectContent align="start" alignItemWithTrigger={false}>
              {SUPPORTED_LANGS.map((lang) => (
                <SelectItem key={lang} value={lang}>
                  {LANG_LABELS[lang] ?? lang}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <ProviderConfigSection
        title={t("settings.asrConfig")}
        icon={<Mic size={18} className="text-muted-foreground" />}
        category="asr"
        presets={providers?.asr ?? []}
        form={asrForm}
        onChange={setAsrForm}
      />

      <ProviderConfigSection
        title={t("settings.llmConfig")}
        icon={<Brain size={18} className="text-muted-foreground" />}
        category="llm"
        presets={providers?.llm ?? []}
        form={llmForm}
        onChange={setLlmForm}
      />

      <CookieCard />

      <div className="flex justify-end">
        <Button
          onClick={() => void handleSave()}
          disabled={saving}
          className="gap-2"
        >
          <Save size={16} />
          {saving ? "..." : t("settings.save")}
        </Button>
      </div>
    </div>
  );
}
