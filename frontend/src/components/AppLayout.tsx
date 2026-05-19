import { useState } from "react";
import { Outlet } from "react-router";
import { useTranslation } from "react-i18next";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sidebar } from "./Sidebar";
import { getAccessToken } from "@/auth/token";

export function AppLayout() {
  const { t } = useTranslation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="h-screen flex bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 min-w-0 flex flex-col h-screen md:ml-52">
        {/* Mobile header */}
        <header className="border-b border-border md:hidden shrink-0">
          <div className="px-4 py-3 flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu size={20} />
            </Button>
            <h1 className="text-base font-bold">{t("app.title")}</h1>
          </div>
        </header>

        {/* Main content — independent scroll */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-5xl mx-auto px-4 py-8 md:px-6">
            <Outlet />
          </div>
        </main>
      </div>
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
