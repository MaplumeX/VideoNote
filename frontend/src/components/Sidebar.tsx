import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useLocation } from "react-router";
import { Plus, FileText, Settings, Globe, LogOut, X, Sun, Moon } from "lucide-react";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/auth/token";
import { Separator } from "@/components/ui/separator";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const appLanguage = i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en";
  const [isDark, setIsDark] = useState(document.documentElement.classList.contains("dark"));

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const navItems = [
    { path: "/app/new", icon: Plus, label: t("sidebar.newNote") },
    { path: "/app/history", icon: FileText, label: t("sidebar.history") },
    { path: "/app/settings", icon: Settings, label: t("sidebar.settings") },
  ];

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + "/");

  const toggleLang = () => {
    const next = appLanguage === "zh-CN" ? "en" : "zh-CN";
    void i18n.changeLanguage(next);
  };

  const toggleTheme = () => {
    document.documentElement.classList.toggle("dark");
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
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/30 md:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed top-0 left-0 z-50 h-screen w-52 border-r border-border bg-sidebar text-sidebar-foreground flex flex-col transition-transform md:translate-x-0 md:z-auto",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 md:py-5 shrink-0">
          <h1 className="text-base font-bold">{t("app.title")}</h1>
          <button onClick={onClose} className="p-1 rounded hover:bg-sidebar-accent md:hidden">
            <X size={18} />
          </button>
        </div>

        <Separator />

        {/* Nav items */}
        <nav className="flex-1 px-2 py-2 space-y-0.5 overflow-y-auto">
          {navItems.map(({ path, icon: Icon, label }) => (
            <button
              key={path}
              onClick={() => {
                navigate(path);
                onClose();
              }}
              className={cn(
                "w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive(path)
                  ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
              )}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>

        <Separator />

        {/* Bottom section */}
        <div className="px-2 py-3 space-y-0.5 shrink-0">
          <button
            onClick={toggleTheme}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground transition-colors"
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
            {isDark ? t("theme.light") : t("theme.dark")}
          </button>
          <button
            onClick={toggleLang}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground transition-colors"
          >
            <Globe size={18} />
            {appLanguage === "zh-CN" ? "English" : "中文"}
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-destructive/10 hover:text-destructive transition-colors"
          >
            <LogOut size={18} />
            {t("auth.signOut")}
          </button>
        </div>
      </aside>
    </>
  );
}
