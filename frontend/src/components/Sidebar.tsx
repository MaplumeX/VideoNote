import { useTranslation } from "react-i18next";
import { useNavigate, useLocation } from "react-router";
import { Plus, FileText, Settings, LogOut, X, Sun, Moon, Monitor, ChevronsLeft, ChevronsRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme, type Theme } from "@/hooks/useTheme";
import { clearAuth } from "@/auth/token";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger, DropdownMenuRadioGroup, DropdownMenuRadioItem } from "@/components/ui/dropdown-menu";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function Sidebar({ open, onClose, collapsed, onToggleCollapse }: SidebarProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, resolvedTheme, setTheme } = useTheme();

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
          "fixed top-0 left-0 z-50 h-screen border-r border-border bg-sidebar text-sidebar-foreground flex flex-col transition-all duration-300 md:translate-x-0 md:z-auto",
          collapsed ? "w-14" : "w-52",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 md:py-5 shrink-0">
          <h1 className={cn("text-base font-bold transition-opacity duration-200", collapsed && "opacity-0 w-0 overflow-hidden")}>{t("app.title")}</h1>
          <Button variant="ghost" size="icon-xs" onClick={onClose} className="md:hidden hover:bg-sidebar-accent">
            <X size={18} />
          </Button>
        </div>

        <Separator />

        {/* Nav items */}
        <nav className="flex-1 px-2 py-2 space-y-0.5 overflow-y-auto">
          {navItems.map(({ path, icon: Icon, label }) =>
            collapsed ? (
              <Tooltip key={path}>
                <TooltipTrigger
                  render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
                    <Button
                      variant="ghost"
                      {...props}
                      onClick={() => {
                        navigate(path);
                        onClose();
                      }}
                      className={cn(
                        "w-full flex items-center justify-center px-0 py-2 text-sm",
                        isActive(path)
                          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground hover:bg-sidebar-accent"
                          : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                      )}
                    >
                      <Icon size={18} />
                    </Button>
                  )}
                />
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            ) : (
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
            )
          )}
        </nav>

        <Separator />

        {/* Bottom section */}
        <div className="px-2 py-3 space-y-0.5 shrink-0">
          {collapsed ? (
            <>
              <DropdownMenu>
                <Tooltip>
                  <TooltipTrigger
                    render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
                      <DropdownMenuTrigger
                        render={(triggerProps) => (
                          <Button
                            variant="ghost"
                            {...props}
                            {...triggerProps}
                            className="w-full flex items-center justify-center px-0 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                          >
                            {resolvedTheme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
                          </Button>
                        )}
                      />
                    )}
                  />
                  <TooltipContent side="right">{t("theme.toggle")}</TooltipContent>
                </Tooltip>
                <DropdownMenuContent side="right" align="start">
                  <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
                    <DropdownMenuRadioItem value="light">
                      <Sun size={14} />
                      {t("theme.light")}
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="dark">
                      <Moon size={14} />
                      {t("theme.dark")}
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="system">
                      <Monitor size={14} />
                      {t("theme.system")}
                    </DropdownMenuRadioItem>
                  </DropdownMenuRadioGroup>
                </DropdownMenuContent>
              </DropdownMenu>
              <Tooltip>
                <TooltipTrigger
                  render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
                    <Button
                      variant="ghost"
                      {...props}
                      onClick={() => { navigate("/app/settings"); onClose(); }}
                      className="w-full flex items-center justify-center px-0 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                    >
                      <Settings size={18} />
                    </Button>
                  )}
                />
                <TooltipContent side="right">{t("sidebar.settings")}</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger
                  render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
                    <Button
                      variant="ghost"
                      {...props}
                      onClick={handleLogout}
                      className="w-full flex items-center justify-center px-0 py-2 text-sm text-sidebar-foreground/70 hover:bg-destructive/10 hover:text-destructive"
                    >
                      <LogOut size={18} />
                    </Button>
                  )}
                />
                <TooltipContent side="right">{t("auth.signOut")}</TooltipContent>
              </Tooltip>
            </>
          ) : (
            <>
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
                    <Button
                      variant="ghost"
                      {...props}
                      className="w-full flex items-center justify-start gap-2.5 px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                    >
                      {resolvedTheme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
                      {t("theme.toggle")}
                    </Button>
                  )}
                />
                <DropdownMenuContent side="top" align="start">
                  <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
                    <DropdownMenuRadioItem value="light">
                      <Sun size={14} />
                      {t("theme.light")}
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="dark">
                      <Moon size={14} />
                      {t("theme.dark")}
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="system">
                      <Monitor size={14} />
                      {t("theme.system")}
                    </DropdownMenuRadioItem>
                  </DropdownMenuRadioGroup>
                </DropdownMenuContent>
              </DropdownMenu>
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
            </>
          )}
          <Separator />
          {collapsed ? (
            <Tooltip>
              <TooltipTrigger
                render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
                  <Button
                    variant="ghost"
                    {...props}
                    onClick={onToggleCollapse}
                    className="w-full flex items-center justify-center px-0 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                  >
                    <ChevronsRight size={18} />
                  </Button>
                )}
              />
              <TooltipContent side="right">{t("sidebar.expand")}</TooltipContent>
            </Tooltip>
          ) : (
            <Button
              variant="ghost"
              onClick={onToggleCollapse}
              className="w-full flex items-center justify-start gap-2.5 px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
            >
              <ChevronsLeft size={18} />
              {t("sidebar.collapse")}
            </Button>
          )}
        </div>
      </aside>
    </>
  );
}
