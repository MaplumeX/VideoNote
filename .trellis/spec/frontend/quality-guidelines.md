# Quality Guidelines

> Code quality standards for frontend development.

---

## Linting & Type Checking

- **TypeScript**: `tsc --noEmit` — zero errors
- **ESLint**: `eslint src/` — zero warnings
- **Build**: `vite build` — must succeed
- **Run from `frontend/` directory**: `tsc` and `vite` require CWD to be the frontend project root

---

## Forbidden Patterns

### Don't: Call setState during render

React StrictMode renders twice. setState in render body = infinite loop.

### Don't: Spread unknown props to native DOM elements

react-markdown, Radix, etc. pass extra props (`node`, `index`, `asChild`) that are not valid HTML attributes. Destructure only what you need.

### Don't: Use `any` type

Use proper types from `@/types/`. If a library lacks types, create a `.d.ts` declaration.

### Don't: Use fetch for file uploads that need progress

Fetch API lacks `upload.onprogress`. Use XHR instead.

---

## Required Patterns

- All user-visible strings must use i18n `t()` — including auth pages, labels, buttons, error messages, and link text
- Auth page actions (loginAction, registerAction) use `new Response(null, {status: 302, headers: {Location: url}})` for redirects — don't import or redefine `redirect` from react-router inside actions
- All components: named exports
- All hooks: `use` prefix, return object (not tuple)
- Styling: Tailwind only via `cn()` utility
- API calls: through `@/api/client.ts`, not inline fetch
- Types: defined in `@/types/index.ts`, kept in sync with backend Pydantic schemas

### i18next Region-Specific Locales

When resources are keyed by exact region codes such as `zh-CN`, keep `supportedLngs`
to those exact app languages and do not enable `nonExplicitSupportedLngs`.

```ts
// Bad: zh-CN can resolve to fallback English while i18n.language still says zh-CN.
nonExplicitSupportedLngs: true;

// Good: zh, zh-Hans-CN, and zh-CN normalize to the zh-CN resource.
supportedLngs: ["en", "zh-CN"];
```

Use `i18n.resolvedLanguage` for UI decisions and normalize outbound API language
values to the app contract (`"en"` or `"zh-CN"`).

---

## Testing Requirements

- Vitest for unit tests
- React Testing Library for component tests
- Test SSE hook with mock EventSource
- Test upload hook with mock XHR
