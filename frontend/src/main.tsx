import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider, redirect } from "react-router";
import "./index.css";
import "./i18n";

import { VideoNoteApp } from "./App";
import { AppLayout, authLoader } from "./components/AppLayout";
import { LoginPage, loginAction } from "./pages/LoginPage";
import { RegisterPage, registerAction } from "./pages/RegisterPage";
import { HistoryPage } from "./pages/HistoryPage";
import { getAccessToken } from "./auth/token";

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
      { index: true, Component: VideoNoteApp },
      { path: "history", Component: HistoryPage },
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
