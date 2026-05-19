import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider, redirect } from "react-router";
import "./index.css";
import "./i18n";

import { DashboardPage } from "./pages/DashboardPage";
import { NewNotePage } from "./pages/NewNotePage";
import { NoteDetailPage } from "./pages/NoteDetailPage";
import { AppLayout, authLoader } from "./components/AppLayout";
import { LoginPage, loginAction } from "./pages/LoginPage";
import { RegisterPage, registerAction } from "./pages/RegisterPage";
import { HistoryPage } from "./pages/HistoryPage";
import { SettingsPage } from "./pages/SettingsPage";
import { getAccessToken } from "./auth/token";
import { silentRefresh } from "./auth/api";

async function bootstrap() {
  await silentRefresh();

  const router = createBrowserRouter([
    {
      path: "/auth/login",
      loader: () => {
        if (getAccessToken()) return redirect("/app");
        return null;
      },
      Component: LoginPage,
      action: loginAction,
    },
    {
      path: "/auth/register",
      loader: () => {
        if (getAccessToken()) return redirect("/app");
        return null;
      },
      Component: RegisterPage,
      action: registerAction,
    },
    {
      path: "/app",
      loader: authLoader,
      Component: AppLayout,
      children: [
        { index: true, Component: DashboardPage },
        { path: "new", Component: NewNotePage },
        { path: "notes/:id", Component: NoteDetailPage },
        { path: "history", Component: HistoryPage },
        { path: "settings", Component: SettingsPage },
      ],
    },
    {
      path: "*",
      loader: () => {
        if (getAccessToken()) return redirect("/app");
        return redirect("/auth/login");
      },
    },
  ]);

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  );
}

void bootstrap();
