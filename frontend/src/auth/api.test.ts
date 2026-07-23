import { beforeEach, describe, expect, it, vi } from "vitest";
import { authFetch, silentRefresh } from "./api";
import { clearAuth, getAccessToken, setAccessToken } from "./token";

function jsonResponse(status: number, body: object): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("authFetch", () => {
  beforeEach(() => {
    clearAuth();
    vi.restoreAllMocks();
  });

  it("shares one refresh request across concurrent 401 responses", async () => {
    setAccessToken("expired");
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/auth/refresh") {
        refreshCalls += 1;
        return jsonResponse(200, { access_token: "fresh" });
      }

      const requestCalls = fetchMock.mock.calls
        .filter(([url]) => String(url) !== "/api/auth/refresh").length;
      return requestCalls <= 2
        ? new Response(null, { status: 401 })
        : new Response(null, { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const responses = await Promise.all([
      authFetch("/api/one"),
      authFetch("/api/two"),
    ]);

    expect(responses.map((response) => response.status)).toEqual([200, 200]);
    expect(refreshCalls).toBe(1);
    expect(getAccessToken()).toBe("fresh");
  });

  it("rejects every waiter when the shared refresh fails", async () => {
    setAccessToken("expired");
    let refreshCalls = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/auth/refresh") {
        refreshCalls += 1;
        return jsonResponse(401, {});
      }
      return new Response(null, { status: 401 });
    }));

    const settled = await Promise.allSettled([
      authFetch("/api/one"),
      authFetch("/api/two"),
    ]);

    expect(settled.every(({ status }) => status === "rejected")).toBe(true);
    expect(refreshCalls).toBe(1);
    expect(getAccessToken()).toBeNull();
  });

  it("retries an original request at most once", async () => {
    setAccessToken("expired");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/auth/refresh") {
        return jsonResponse(200, { access_token: "fresh" });
      }
      return new Response(null, { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await authFetch("/api/protected");

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shares the refresh request with silentRefresh", async () => {
    setAccessToken("expired");
    let finishRefresh: ((response: Response) => void) | undefined;
    const pendingRefresh = new Promise<Response>((resolve) => {
      finishRefresh = resolve;
    });
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      if (String(input) === "/api/auth/refresh") {
        refreshCalls += 1;
        return pendingRefresh;
      }
      const token = new Headers(init?.headers).get("Authorization");
      return new Response(null, {
        status: token === "Bearer fresh" ? 200 : 401,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const request = authFetch("/api/protected");
    const silent = silentRefresh();
    finishRefresh?.(jsonResponse(200, { access_token: "fresh" }));

    await expect(silent).resolves.toBe(true);
    await expect(request).resolves.toMatchObject({ status: 200 });
    expect(refreshCalls).toBe(1);
  });

  it("retries a late old-token 401 with the latest token without refreshing again", async () => {
    setAccessToken("expired");
    let finishLateRequest: ((response: Response) => void) | undefined;
    const lateResponse = new Promise<Response>((resolve) => {
      finishLateRequest = resolve;
    });
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = String(input);
      if (url === "/api/auth/refresh") {
        refreshCalls += 1;
        return jsonResponse(200, { access_token: "fresh" });
      }

      const token = new Headers(init?.headers).get("Authorization");
      if (url === "/api/late" && token === "Bearer expired") {
        return lateResponse;
      }
      return new Response(null, {
        status: token === "Bearer fresh" ? 200 : 401,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const firstRequest = authFetch("/api/first");
    const lateRequest = authFetch("/api/late");
    await expect(firstRequest).resolves.toMatchObject({ status: 200 });
    expect(getAccessToken()).toBe("fresh");

    finishLateRequest?.(new Response(null, { status: 401 }));
    await expect(lateRequest).resolves.toMatchObject({ status: 200 });
    expect(refreshCalls).toBe(1);
  });

  it("does not refresh again when a late old-token 401 arrives after refresh failed", async () => {
    setAccessToken("expired");
    let finishLateRequest: ((response: Response) => void) | undefined;
    const lateResponse = new Promise<Response>((resolve) => {
      finishLateRequest = resolve;
    });
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/refresh") {
        refreshCalls += 1;
        return jsonResponse(401, {});
      }
      if (url === "/api/late") {
        return lateResponse;
      }
      return new Response(null, { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const firstRequest = authFetch("/api/first");
    const lateRequest = authFetch("/api/late");
    await expect(firstRequest).rejects.toBeDefined();
    expect(getAccessToken()).toBeNull();

    finishLateRequest?.(new Response(null, { status: 401 }));
    await expect(lateRequest).rejects.toBeDefined();
    expect(refreshCalls).toBe(1);
  });
});
