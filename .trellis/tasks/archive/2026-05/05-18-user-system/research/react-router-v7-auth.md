# Research: React Router v7 Authentication Flow Patterns

- **Query**: React Router v7 auth flow patterns for SPA (BrowserRouter vs createBrowserRouter, protected routes, JWT token management, token refresh, login/register structure, redirect patterns)
- **Scope**: Mixed (internal codebase analysis + external React Router v7 docs)
- **Date**: 2026-05-18

## Findings

### 1. React Router v7 Setup: BrowserRouter vs createBrowserRouter

React Router v7 (latest: 7.15.1) offers **three modes**: Framework, Data, and Declarative.

| Mode | Router API | Data Loading | Auth-Relevant Features |
|------|-----------|-------------|----------------------|
| **Declarative** | `<BrowserRouter>`, `<Routes>`, `<Route>` | None (manual) | Simplest; no loaders/actions; auth must be done at component level |
| **Data** | `createBrowserRouter()` + `RouterProvider` | `loader`, `action` on route objects | Preferred for auth: loaders can check auth before rendering, actions handle login/logout |
| **Framework** | File-based routing via `@react-router/dev` | `loader`, `action`, `clientLoader`, `clientAction` | Full-featured; SPA mode available via `ssr: false` in config |

**For this project (React 19 + Vite SPA)**: The **Data mode** (`createBrowserRouter`) is the recommended choice because:

- It provides `loader` functions that run **before** a route renders -- ideal for auth checks
- It provides `action` functions for form submissions -- ideal for login/register mutations
- It supports `redirect()` from loaders/actions -- ideal for auth redirects
- It works with Vite without needing the `@react-router/dev` build plugin
- The Declarative mode (`<BrowserRouter>`) is simpler but lacks data loading, meaning auth checks must be done manually in components or effects, which is less robust

**Declarative mode setup** (simpler but no data APIs):
```tsx
import { BrowserRouter, Routes, Route } from "react-router";

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<App />} />
    </Routes>
  </BrowserRouter>
);
```

**Data mode setup** (recommended for auth):
```tsx
import { createBrowserRouter, RouterProvider } from "react-router/dom";

const router = createBrowserRouter([
  {
    path: "/",
    Component: App,
    children: [
      { index: true, Component: Home },
      { path: "login", Component: Login },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <RouterProvider router={router} />
);
```

**Installation**: `npm i react-router` (single package, v7.15.1)

### 2. Protected Route Patterns

There are three main patterns for protecting routes:

#### Pattern A: Loader-level redirect (Data mode only -- recommended)

The `loader` function runs before the component renders. If auth fails, `redirect()` to login before any UI paints.

```tsx
import { redirect } from "react-router";

function requireAuth() {
  // Check auth state (from memory, localStorage, etc.)
  const token = getAccessToken();
  if (!token) {
    throw redirect("/login");
  }
}

// In route config:
{
  path: "dashboard",
  loader: async () => {
    requireAuth(); // throws redirect if not authenticated
    const data = await fetchDashboard();
    return data;
  },
  Component: Dashboard,
}
```

Key: `redirect()` from `react-router` throws a special response that the router catches. The component never mounts if auth fails.

#### Pattern B: Layout route guard (Data mode)

Use a layout route with an `<Outlet>` that checks auth in its loader. All protected child routes inherit the guard.

```tsx
// Auth layout that guards all children
{
  path: "app",
  loader: async () => {
    const user = await getCurrentUser(); // throws redirect if not authed
    return { user };
  },
  Component: AuthLayout, // renders <Outlet />
  children: [
    { index: true, Component: Home },
    { path: "settings", Component: Settings },
  ],
}

function AuthLayout() {
  const { user } = useLoaderData();
  return (
    <div>
      <nav>{user.name}</nav>
      <Outlet />
    </div>
  );
}
```

#### Pattern C: Component-level check (Declarative or Data mode)

A wrapper component that checks auth in `useEffect` or render. Less robust because the component briefly mounts before redirecting.

```tsx
function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = getAccessToken();
  const navigate = useNavigate();
  const location = useLocation();

  if (!token) {
    // Save the attempted URL for redirect after login
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}

// Usage in route config:
{ path: "dashboard", element: <RequireAuth><Dashboard /></RequireAuth> }
```

**Comparison**:

| Approach | When Auth Check Happens | Flash of Unprotected Content | Requires Data Mode |
|----------|------------------------|------------------------------|-------------------|
| Loader redirect | Before render | No | Yes |
| Layout route guard | Before render | No | Yes |
| Component check | During render | Possible (brief) | No |

**Recommendation for this project**: Pattern B (Layout route guard) because it avoids code duplication across routes and naturally provides the authenticated user data to all protected child routes via `useLoaderData`.

### 3. Auth State Management: JWT Token Storage

Since the backend sends JWT access + refresh tokens, the frontend must decide where to store them.

| Storage | XSS-Safe | CSRF-Safe | Persistent | Auto-Sent | Best For |
|---------|---------|-----------|------------|-----------|----------|
| **httpOnly cookie** | Yes (JS cannot read) | No (needs CSRF token) | Yes | Yes (browser auto-sends) | Server-rendered apps |
| **localStorage** | No (JS can read) | Yes | Yes | No | SPAs with custom fetch |
| **Memory only** | No (but harder to access) | Yes | No (lost on refresh) | No | High-security apps |
| **sessionStorage** | No | Yes | Tab-only | No | Per-tab sessions |

**For this project's SPA architecture**:

- **Access token**: Store in **memory** (JS variable / React context / module-level variable). Short-lived (5-15 min). Lost on page refresh, but that is acceptable because the refresh token restores it.
- **Refresh token**: If the backend sends it as an `httpOnly` cookie, the browser will automatically include it on refresh requests. If sent in the response body, store in **localStorage** -- this is the simpler SPA approach but has XSS exposure.
- **Why not localStorage for access token**: localStorage is accessible to any JS running on the page (including XSS). Storing the access token there makes token theft easier. Memory-only access token limits the damage window.

**Practical pattern for this project**:

```tsx
// src/auth/token.ts (module-level state)
let accessToken: string | null = null;

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

// Refresh token: if backend uses httpOnly cookie, it is auto-sent.
// If backend sends it in response body, store in localStorage:
export function getRefreshToken() {
  return localStorage.getItem("refresh_token");
}
export function setRefreshToken(token: string | null) {
  if (token) localStorage.setItem("refresh_token", token);
  else localStorage.removeItem("refresh_token");
}
```

**Important**: The current `api/client.ts` uses plain `fetch` without any auth headers. It will need to be extended to include `Authorization: Bearer <token>` on requests, and to handle 401 responses for token refresh (see section 4).

### 4. Token Refresh Flow in Frontend

When a request returns 401, the frontend should:

1. Pause all in-flight requests
2. Attempt to refresh the access token using the refresh token
3. If refresh succeeds: retry all paused requests with the new access token
4. If refresh fails: clear auth state and redirect to login

**Pattern: Intercepting fetch with a wrapper**

```tsx
// src/api/client.ts
let isRefreshing = false;
let pendingRequests: Array<() => void> = [];

async function refreshToken(): Promise<string> {
  const res = await fetch("/api/auth/refresh", {
    method: "POST",
    // If refresh token is in httpOnly cookie, no body needed.
    // If in localStorage, send it:
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: getRefreshToken() }),
  });

  if (!res.ok) {
    // Refresh failed -- clear everything and redirect to login
    setAccessToken(null);
    setRefreshToken(null);
    throw redirect("/login");
  }

  const data = await res.json();
  setAccessToken(data.access_token);
  if (data.refresh_token) setRefreshToken(data.refresh_token);
  return data.access_token;
}

export async function authFetch(url: string, options: RequestInit = {}) {
  const token = getAccessToken();
  const headers = {
    ...options.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401 && token) {
    if (!isRefreshing) {
      isRefreshing = true;
      try {
        const newToken = await refreshToken();
        isRefreshing = false;
        // Resolve all pending requests
        pendingRequests.forEach((cb) => cb());
        pendingRequests = [];
        // Retry this request with new token
        return authFetch(url, {
          ...options,
          headers: { ...options.headers, Authorization: `Bearer ${newToken}` },
        });
      } catch {
        isRefreshing = false;
        pendingRequests = [];
        throw redirect("/login");
      }
    }

    // Another request is already refreshing -- wait for it
    return new Promise<Response>((resolve) => {
      pendingRequests.push(() => {
        const newToken = getAccessToken();
        resolve(
          authFetch(url, {
            ...options,
            headers: {
              ...options.headers,
              ...(newToken ? { Authorization: `Bearer ${newToken}` } : {}),
            },
          })
        );
      });
    });
  }

  return res;
}
```

**Alternative: Use the `clientLoader` / `clientAction` pattern (Framework/Data mode)**

In Data mode with `createBrowserRouter`, loaders run before rendering. If a loader's fetch returns 401, the loader can call `refreshToken()` and retry, or throw `redirect("/login")`. This means each protected route's loader handles refresh naturally.

However, this approach does NOT batch concurrent refresh requests. The wrapper function above is still recommended as the single source of truth for API calls.

### 5. Login/Register Page Structure with React Router

**Route configuration**:

```tsx
const router = createBrowserRouter([
  {
    path: "/",
    Component: RootLayout,
    children: [
      // Public routes (no auth needed)
      { index: true, Component: LandingPage },
      {
        path: "auth",
        Component: AuthLayout,
        children: [
          { path: "login", Component: LoginPage, action: loginAction },
          { path: "register", Component: RegisterPage, action: registerAction },
        ],
      },
      // Protected routes (auth required)
      {
        path: "app",
        loader: authLoader, // checks auth, throws redirect if not authenticated
        Component: AppLayout,
        children: [
          { index: true, Component: HomePage },
          { path: "history", Component: HistoryPage },
        ],
      },
    ],
  },
]);
```

**Login page with Data mode action**:

```tsx
// LoginPage.tsx
import { Form, useActionData, useNavigation } from "react-router";

export async function loginAction({ request }: { request: Request }) {
  const formData = await request.formData();
  const email = formData.get("email");
  const password = formData.get("password");

  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const data = await res.json();
    return { error: data.detail || "Login failed" };
  }

  const data = await res.json();
  setAccessToken(data.access_token);
  if (data.refresh_token) setRefreshToken(data.refresh_token);

  // Redirect to the page the user was trying to visit, or home
  const url = new URL(request.url);
  const redirectTo = url.searchParams.get("redirect") || "/app";
  return redirect(redirectTo);
}

export function LoginPage() {
  const actionData = useActionData() as { error?: string } | undefined;
  const navigation = useNavigation();
  const isSubmitting = navigation.state === "submitting";

  return (
    <div>
      {actionData?.error && <div className="text-red-500">{actionData.error}</div>}
      <Form method="post">
        <label>
          Email: <input type="email" name="email" required />
        </label>
        <label>
          Password: <input type="password" name="password" required />
        </label>
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Logging in..." : "Log In"}
        </button>
      </Form>
    </div>
  );
}
```

**Key points**:
- `<Form method="post">` from `react-router` automatically calls the route's `action` function
- `useActionData()` returns the data from the action (error messages)
- `useNavigation()` tracks submission state for loading UI
- After successful login, `redirect()` sends the user to the intended destination

### 6. Redirect Patterns

#### Unauthenticated user -> Login

**In a loader (Data mode, recommended)**:
```tsx
import { redirect } from "react-router";

function authLoader({ request }: { request: Request }) {
  const token = getAccessToken();
  if (!token) {
    const url = new URL(request.url);
    // Pass the attempted URL so we can redirect back after login
    const redirectTo = encodeURIComponent(url.pathname + url.search);
    throw redirect(`/auth/login?redirect=${redirectTo}`);
  }
  return null;
}
```

**In a component (Declarative mode)**:
```tsx
import { Navigate, useLocation } from "react-router";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = getAccessToken();
  const location = useLocation();

  if (!token) {
    return (
      <Navigate
        to="/auth/login"
        state={{ from: location.pathname }}
        replace
      />
    );
  }
  return <>{children}</>;
}
```

#### Login success -> Original destination or home

In the login action:
```tsx
export async function loginAction({ request }: { request: Request }) {
  // ... authentication logic ...
  const url = new URL(request.url);
  const redirectTo = url.searchParams.get("redirect") || "/app";
  return redirect(redirectTo);
}
```

Or with `location.state` (Declarative approach):
```tsx
function LoginSuccess() {
  const location = useLocation();
  const from = (location.state as { from?: string })?.from || "/app";
  return <Navigate to={from} replace />;
}
```

#### Already authenticated -> Skip login page

In the login route's loader:
```tsx
{
  path: "login",
  loader: () => {
    const token = getAccessToken();
    if (token) return redirect("/app");
    return null;
  },
  Component: LoginPage,
  action: loginAction,
}
```

### Current Project Context

#### Files Found

| File Path | Description |
|---|---|
| `frontend/src/main.tsx` | React entry point, currently renders `<App />` directly with `createRoot` -- no router |
| `frontend/src/App.tsx` | Root component, uses `AppStep` state ("input" / "processing" / "result") for page switching -- no routing |
| `frontend/src/api/client.ts` | API client using plain `fetch`, no auth headers, calls `/api/process` and `/api/tasks/:id/result` |
| `frontend/src/types/index.ts` | Type definitions for `TaskProgress`, `NoteResult`, `ProcessResponse` |
| `frontend/src/hooks/useSSE.ts` | SSE hook for progress updates |
| `frontend/src/hooks/useVideoUpload.ts` | XHR upload hook |
| `frontend/src/components/VideoInput.tsx` | Video input component |
| `frontend/src/components/ProgressBar.tsx` | Progress display component |
| `frontend/src/components/NoteView.tsx` | Markdown note renderer |
| `frontend/package.json` | Dependencies -- NO react-router installed yet |
| `backend/app/api/routes.py` | FastAPI routes -- NO auth endpoints yet |
| `backend/app/main.py` | FastAPI app -- CORS allows all origins, no auth middleware |

#### Code Patterns

- **Current navigation**: State-driven (`AppStep` type in `App.tsx:11`). No URL changes when switching between input/processing/result steps.
- **API calls**: Direct `fetch()` in `client.ts`, no auth headers. Functions return typed responses.
- **No global state**: App state lives in `App.tsx` component. Hooks (`useSSE`, `useVideoUpload`) manage their own local state.
- **Named exports**: Components use `export function` pattern (per spec).

#### Migration Path

Adding auth + routing requires:

1. Install: `npm i react-router`
2. Replace `App.tsx` step state with URL-based routes via `createBrowserRouter`
3. Create auth module (`src/auth/`) with token management
4. Create login/register page components
5. Extend `api/client.ts` with auth header injection and 401 refresh handling
6. Add `authLoader` to protected routes
7. Add backend auth endpoints (login, register, refresh, logout)

### External References

- [React Router v7 Declarative Installation](https://reactrouter.com/start/declarative/installation) -- BrowserRouter setup
- [React Router v7 Data Mode Installation](https://reactrouter.com/start/data/installation) -- createBrowserRouter setup
- [React Router v7 Data Mode Routing](https://reactrouter.com/start/data/routing) -- Route objects, nested routes, loaders
- [React Router v7 Data Loading](https://reactrouter.com/start/data/data-loading) -- Loader functions
- [React Router v7 Actions](https://reactrouter.com/start/data/actions) -- Action functions for mutations (login, register)
- [React Router v7 SPA Guide](https://reactrouter.com/how-to/spa) -- SPA mode with `ssr: false` in framework config
- [React Router v7 Sessions and Cookies](https://reactrouter.com/explanation/sessions-and-cookies) -- Server-side session management (framework mode; not directly applicable to pure SPA with external JWT backend)
- [React Router v7 Security](https://reactrouter.com/how-to/security) -- Security best practices
- [React Router v7 Address Book Tutorial](https://reactrouter.com/tutorials/address-book) -- Complete app example with loaders, actions, forms

### Related Specs

- `.trellis/spec/frontend/directory-structure.md` -- Current directory layout (will need `auth/`, `pages/` additions)
- `.trellis/spec/frontend/state-management.md` -- Currently unfilled; auth state should be documented here
- `.trellis/spec/frontend/component-guidelines.md` -- Named exports, Tailwind-only styling, `cn()` utility
- `.trellis/spec/frontend/hook-guidelines.md` -- Custom hook patterns (`use` prefix, return objects)

## Caveats / Not Found

- **No existing auth code**: The backend has zero auth-related routes, middleware, or user models. Both frontend and backend auth need to be built from scratch.
- **No react-router installed**: `package.json` does not include `react-router` or any routing library.
- **Framework mode vs Data mode**: Framework mode (file-based routing with `@react-router/dev`) requires a build plugin and `react-router.config.ts`. For this existing Vite project, Data mode (`createBrowserRouter`) is a simpler integration that does not require ejecting or restructuring the build pipeline.
- **Server-side session utilities**: React Router v7's `createCookieSessionStorage` and related APIs are designed for server-side (framework/Data mode with SSR). For a pure SPA that calls a separate backend API, these are not applicable. Token management must be done in client-side JS.
- **Token refresh race condition**: The concurrent-request batching pattern in section 4 is essential. Without it, if multiple API calls fail with 401 at the same time, each would trigger a separate refresh request, causing token overwrites and potential failures.
- **SSR safety note**: Even in SPA mode, React Router Framework mode requires routes to be SSR-safe (no `window` access during initial render). With Data mode (`createBrowserRouter`), this is not a concern since there is no server rendering at all.
