import { getAccessToken, setAccessToken, clearAuth } from "./token";
import { redirect } from "react-router";

const API_BASE = "/api";

let isRefreshing = false;
let pendingRequests: Array<(token: string) => void> = [];

async function refreshToken(): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });

  if (!res.ok) {
    clearAuth();
    throw redirect("/auth/login");
  }

  const data = await res.json();
  setAccessToken(data.access_token);
  return data.access_token;
}

export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getAccessToken();
  const headers = {
    ...options.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(url, { ...options, headers, credentials: "include" });

  if (res.status === 401 && token) {
    if (!isRefreshing) {
      isRefreshing = true;
      try {
        const newToken = await refreshToken();
        isRefreshing = false;
        const callbacks = pendingRequests;
        pendingRequests = [];
        callbacks.forEach((cb) => cb(newToken));

        return authFetch(url, {
          ...options,
          headers: { ...options.headers, Authorization: `Bearer ${newToken}` },
        });
      } catch (err) {
        isRefreshing = false;
        pendingRequests = [];
        throw err;
      }
    }

    return new Promise<Response>((resolve) => {
      pendingRequests.push((newToken: string) => {
        resolve(
          authFetch(url, {
            ...options,
            headers: { ...options.headers, Authorization: `Bearer ${newToken}` },
          })
        );
      });
    });
  }

  return res;
}
