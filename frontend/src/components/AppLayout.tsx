import { Outlet, useNavigate, useLocation } from "react-router";
import { useTranslation } from "react-i18next";
import { getAccessToken, clearAuth } from "@/auth/token";
import { Globe, LogOut, FileText, Plus } from "lucide-react";

export function AppLayout() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const appLanguage = i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en";

  const toggleLang = () => {
    const next = appLanguage === "zh-CN" ? "en" : "zh-CN";
    void i18n.changeLanguage(next);
  };

  const handleLogout = async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    }).catch(() => {});
    clearAuth();
    navigate("/auth/login");
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">{t("app.title")}</h1>
            <p className="text-sm text-muted-foreground">{t("app.subtitle")}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate("/app")}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted transition-colors"
            >
              <Plus size={14} />
              {t("auth.newVideo")}
            </button>
            <button
              onClick={() => navigate("/app/history")}
              className={`inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted transition-colors ${
                location.pathname === "/app/history" ? "bg-muted" : ""
              }`}
            >
              <FileText size={14} />
              {t("auth.history")}
            </button>
            <button
              onClick={toggleLang}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted transition-colors"
              aria-label={t("lang.label")}
            >
              <Globe size={14} />
              {t("lang.switch")}
            </button>
            <button
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted transition-colors text-destructive"
            >
              <LogOut size={14} />
              {t("auth.signOut")}
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}

export function authLoader({ request }: { request: Request }) {
  const token = getAccessToken();
  if (!token) {
    const url = new URL(request.url);
    const redirectTo = encodeURIComponent(url.pathname + url.search);
    throw new Response(null, {
      status: 302,
      headers: { Location: `/auth/login?redirect=${redirectTo}` },
    });
  }
  return null;
}
