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

- All components: named exports
- All hooks: `use` prefix, return object (not tuple)
- Styling: Tailwind only via `cn()` utility
- API calls: through `@/api/client.ts`, not inline fetch
- Types: defined in `@/types/index.ts`, kept in sync with backend Pydantic schemas

---

## Testing Requirements

- Vitest for unit tests
- React Testing Library for component tests
- Test SSE hook with mock EventSource
- Test upload hook with mock XHR
