import { useTranslation } from "react-i18next";
import { useNavigate, useLocation } from "react-router";
import { Plus, FileText, Settings, LogOut, X, Sun, Moon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/hooks/useTheme";
import { clearAuth } from "@/auth/token";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();

  const navItems = [
    { path: "/app/new", icon: Plus, label: t("sidebar.newNote") },
    { path: "/app/history", icon: FileText, label: t("sidebar.history") },
  ];

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + "/");

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
          <Button variant="ghost" size="icon-xs" onClick={onClose} className="md:hidden hover:bg-sidebar-accent">
            <X size={18} />
          </Button>
        </div>

        <Separator />

        {/* Nav items */}
        <nav className="flex-1 px-2 py-2 space-y-0.5 overflow-y-auto">
          {navItems.map(({ path, icon: Icon, label }) => (
            <Button
              key={path}
              variant="ghost"
              onClick={() => {
                navigate(path);
                onClose();
              }}
              className={cn(
                "w-full flex items-center justify-start gap-2.5 px-3 py-2 text-sm",
                isActive(path)
                  ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground hover:bg-sidebar-accent"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
              )}
            >
              <Icon size={18} />
              {label}
            </Button>
          ))}
        </nav>

        <Separator />

        {/* Bottom section */}
        <div className="px-2 py-3 space-y-0.5 shrink-0">
          <Button
            variant="ghost"
            onClick={toggleTheme}
            className="w-full flex items-center justify-start gap-2.5 px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            {theme === "dark" ? t("theme.light") : t("theme.dark")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => { navigate("/app/settings"); onClose(); }}
            className="w-full flex items-center justify-start gap-2.5 px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
          >
            <Settings size={18} />
            {t("sidebar.settings")}
          </Button>
          <Button
            variant="ghost"
            onClick={handleLogout}
            className="w-full flex items-center justify-start gap-2.5 px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-destructive/10 hover:text-destructive"
          >
            <LogOut size={18} />
            {t("auth.signOut")}
          </Button>
        </div>
      </aside>
    </>
  );
}
