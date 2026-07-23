import { getAccessToken, setAccessToken, clearAuth } from "./token";
import { redirect } from "react-router";

const API_BASE = "/api";

let refreshPromise: Promise<string> | null = null;

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

function getRefreshPromise(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        return await refreshToken();
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

export async function silentRefresh(): Promise<boolean> {
  try {
    await getRefreshPromise();
    return true;
  } catch {
    return false;
  }
}

async function authFetchWithRetry(
  url: string,
  options: RequestInit,
  alreadyRetried: boolean,
  requestToken: string | null = getAccessToken(),
): Promise<Response> {
  const headers = {
    ...options.headers,
    ...(requestToken ? { Authorization: `Bearer ${requestToken}` } : {}),
  };

  const res = await fetch(url, { ...options, headers, credentials: "include" });

  if (res.status === 401 && requestToken && !alreadyRetried) {
    const latestToken = getAccessToken();
    if (latestToken !== requestToken) {
      if (latestToken) {
        return authFetchWithRetry(url, options, true, latestToken);
      }
      throw redirect("/auth/login");
    }

    await getRefreshPromise();
    return authFetchWithRetry(url, options, true, getAccessToken());
  }

  return res;
}

export function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  return authFetchWithRetry(url, options, false);
}
