import { useTranslation } from "react-i18next";
import { useNavigate, useLocation } from "react-router";
import { Plus, FileText, Settings, LogOut, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/auth/token";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const navItems = [
    { path: "/app/new", icon: Plus, label: t("sidebar.newNote") },
    { path: "/app/history", icon: FileText, label: t("sidebar.history") },
    { path: "/app/settings", icon: Settings, label: t("sidebar.settings") },
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
          "fixed top-0 left-0 z-50 h-full w-52 border-r border-border bg-background flex flex-col transition-transform md:translate-x-0 md:static md:z-auto",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Close button (mobile only) */}
        <div className="flex items-center justify-between px-4 py-4 md:py-5">
          <h1 className="text-base font-bold">{t("app.title")}</h1>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted md:hidden">
            <X size={18} />
          </button>
        </div>

        {/* Nav items */}
        <nav className="flex-1 px-2 space-y-0.5">
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
                  ? "bg-muted font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
              )}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>

        {/* Bottom section */}
        <div className="border-t border-border px-2 py-3 space-y-0.5">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
          >
            <LogOut size={18} />
            {t("auth.signOut")}
          </button>
        </div>
      </aside>
    </>
  );
}
