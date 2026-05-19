import { useState } from "react";
import { Outlet } from "react-router";
import { useTranslation } from "react-i18next";
import { Menu } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { getAccessToken } from "@/auth/token";

export function AppLayout() {
  const { t } = useTranslation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 min-w-0">
        {/* Mobile header */}
        <header className="border-b border-border md:hidden">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 rounded-lg hover:bg-muted transition-colors"
            >
              <Menu size={20} />
            </button>
            <h1 className="text-base font-bold">{t("app.title")}</h1>
          </div>
        </header>

        {/* Main content */}
        <main className="max-w-5xl mx-auto px-4 py-8 md:px-6">
          <Outlet />
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
