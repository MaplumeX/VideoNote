# Research: React i18n Library Comparison

- **Query**: Compare react-i18next, react-intl, and custom lightweight solution for React 19 + Vite + TypeScript project
- **Scope**: Mixed (internal codebase analysis + external library research)
- **Date**: 2026-05-17

## Findings

### Project Context

| File Path | Description |
|---|---|
| `frontend/src/App.tsx` | Main app component; 7 hardcoded strings |
| `frontend/src/components/VideoInput.tsx` | URL/upload input; 6 hardcoded strings |
| `frontend/src/components/ProgressBar.tsx` | Progress display; STAGE_LABELS map with 7 stage names |
| `frontend/src/components/NoteView.tsx` | Markdown note viewer; 0 hardcoded UI strings |

Total: ~20 hardcoded UI strings across 4 components. No NoteView i18n needed (renders markdown content from backend).

Current stack: React 19.1, Vite 6.3, TypeScript 5.8, Tailwind CSS 4.1, no existing i18n.

---

### Option 1: react-i18next (with i18next)

**Bundle Size (package tgz)**:
- i18next: 120 KB tgz, 510 KB unpacked (19 files)
- react-i18next: 220 KB tgz (92 files)
- Additional deps: `use-sync-external-store` (4.2 KB), `html-parse-stringify` (10.7 KB), `@babel/runtime`
- **Combined total: ~345 KB tgz** (before tree-shaking)

**React 19 Compatibility**:
- `peerDependencies.react: ">= 16.8.0"` — explicitly supports React 19
- **Known issue fixed**: PR #1846 fixed `element.ref` deprecation in React 19 (merged 2025-05-22, included in v17.0.5+)
- **Known issue fixed**: PR #1840 added `"use client"` directive for React 19 compat (mainly for Next.js RSC, not relevant for Vite)
- Current version 17.0.8 (released 2026-05-14) — active maintenance

**TypeScript Support**:
- Ships with built-in `.d.ts` and `.d.mts` type definitions
- Supports `i18next-typescript` CLI tool for auto-generating type-safe translation keys (v0.1.0, community-maintained, not actively updated)
- Can configure `i18next` `resources` type for compile-time key checking

**Developer Experience**:
- Setup: create i18n config, wrap app with `I18nextProvider`, use `useTranslation()` hook
- Interpolation: `t('key', { name: 'value' })`
- Pluralization: built-in (keys like `key_one`, `key_other`)
- Lazy loading: `i18next-http-backend` or `i18next-resources-to-backend`
- Detection: `i18next-browser-languagedetector`
- Trans component for inline HTML in translations: `<Trans>i18n in <strong>React</strong></Trans>`
- Rich ecosystem: many plugins, backends, frameworks

**Community / Maintenance**:
- npm weekly downloads: **12.7M** (react-i18next), 17.8M (i18next)
- Latest release: 2026-05-14 (v17.0.8)
- Repository: https://github.com/i18next/react-i18next
- Very active: multiple releases per month, React 19 issues addressed promptly

**Feature Set Summary**: Pluralization (yes), interpolation (yes), lazy loading (yes, via plugin), language detection (yes, via plugin), namespaces (yes), fallback languages (yes), SSR support (yes, not needed here), ICU format (via plugin `i18next-icu`).

---

### Option 2: react-intl (FormatJS)

**Bundle Size (package tgz)**:
- react-intl: 41 KB tgz (10 files)
- @formatjs/intl: 19 KB tgz
- @formatjs/icu-messageformat-parser: 45.6 KB tgz
- intl-messageformat: 27.4 KB tgz
- **Combined total: ~133 KB tgz** (before tree-shaking)
- Note: FormatJS also polyfills Intl APIs for older browsers; modern browsers should not need polyfills

**React 19 Compatibility**:
- `peerDependencies.react: "19"` — explicitly targets React 19
- `peerDependencies.@types/react: "19"` — types aligned with React 19
- Current version 10.1.7 (released 2026-05-15)

**TypeScript Support**:
- Built-in TypeScript definitions
- `defineMessages()` for typed message declarations
- Strong typing for ICU message format arguments

**Developer Experience**:
- Setup: wrap app with `IntlProvider`, use `useIntl()` hook or `<FormattedMessage>` component
- Interpolation: ICU format — `Hello, {name}` with `{name}` typed in the message
- Pluralization: ICU format — `{count, plural, one {item} other {items}}`
- Lazy loading: `@formatjs/cli` for extraction; dynamic locale loading is manual
- Detection: manual (use `navigator.language` or a detection lib)
- Extraction tool: `@formatjs/cli` can extract messages from code automatically
- More verbose syntax for complex messages; simpler for key-value is overkill

**Community / Maintenance**:
- npm weekly downloads: **3.3M** (react-intl), 3.4M (@formatjs/intl)
- Latest release: 2026-05-15 (v10.1.7)
- Repository: https://github.com/formatjs/formatjs
- Active maintenance but smaller community than react-i18next

**Feature Set Summary**: Pluralization (yes, ICU), interpolation (yes, typed), lazy loading (manual), language detection (manual), namespaces (no built-in concept), fallback messages (yes), ICU message format (yes, this is the main selling point), date/number formatting (yes, via Intl APIs).

---

### Option 3: Custom Lightweight Solution (React Context + JSON)

**Bundle Size**:
- Zero dependencies
- Estimated: ~2-5 KB for a minimal implementation (Context, Provider, useTranslation hook, JSON loader)

**React 19 Compatibility**:
- Fully compatible — uses only React built-in APIs (Context, useState, useEffect)

**TypeScript Support**:
- Fully typed with generics: define `TranslationKey` type from JSON shape
- No external types needed

**Developer Experience**:
- Setup: create TranslationContext, Provider, useTranslation hook; import JSON files per locale
- Interpolation: implement simple `replace {{key}}` or template literals
- Pluralization: manual (branch on count in component)
- Lazy loading: dynamic `import()` for locale JSON
- Detection: `navigator.language` parsing (5 lines of code)
- Very simple for key-value use case; no learning curve
- No extraction tools, no ecosystem

**Community / Maintenance**:
- No package; self-maintained
- Risk: as app grows, features like pluralization, fallback, namespaces need manual reimplementation
- No CLI tools for extraction or validation

**Feature Set Summary**: Pluralization (manual), interpolation (simple), lazy loading (dynamic import), language detection (manual, trivial), namespaces (manual), fallback (manual), ICU format (no).

---

## Comparative Summary

| Criterion | react-i18next | react-intl | Custom Context |
|---|---|---|---|
| **Bundle (tgz, pre-tree-shake)** | ~345 KB | ~133 KB | ~0 KB (inline) |
| **Bundle (estimated gzipped)** | ~30-40 KB | ~20-30 KB | ~1-3 KB |
| **React 19 compat** | Yes (issues fixed in v17.0.5+) | Yes (targets React 19) | Yes |
| **TypeScript** | Built-in + optional CLI | Built-in | Manual, fully typed |
| **Setup complexity** | Medium (config + provider) | Medium (provider + messages) | Low (context + JSON) |
| **Weekly npm downloads** | 12.7M | 3.3M | N/A |
| **Pluralization** | Built-in | Built-in (ICU) | Manual |
| **Interpolation** | `{{key}}` | ICU `{key}` | Custom `{{key}}` |
| **Lazy loading** | Plugin | Manual | `import()` |
| **Language detection** | Plugin | Manual | Manual |
| **Key validation** | Optional (i18next-typescript) | defineMessages() | TS generics |
| **Ecosystem / plugins** | Very rich | Moderate (FormatJS) | None |
| **Overkill for ~20 strings?** | Somewhat | Yes | No |

## Key Observations

1. **react-i18next** is battle-tested with React 19. The two React 19 compatibility issues (ref access, "use client" directive) are both fixed in v17.0.5+. Current version 17.0.8 is stable.

2. **react-intl** explicitly targets React 19 and has smaller package size, but its ICU message format is heavier DX for simple key-value translations. The extraction tooling is overkill for 20 strings.

3. **Custom solution** fits the project constraints perfectly: ~20 strings, no SSR, no routing-based locale, key-value with basic interpolation. The bundle overhead is near-zero. The risk is future growth requiring reimplementation of features.

4. For a small app with ~20 strings and only basic interpolation needs, the bundle overhead of react-i18next (~30-40 KB gzipped) or react-intl (~20-30 KB gzipped) is measurable but not catastrophic. The question is whether ecosystem benefits justify the weight.

5. **i18next with lazy loading**: react-i18next supports loading translation files on demand via `i18next-http-backend` or `i18next-resources-to-backend`. With Vite, you can also use dynamic `import()` to load locale JSON only when the user switches language.

6. **react-i18next tree-shaking**: The core `useTranslation` hook and `t` function tree-shake well. The `<Trans>` component adds more weight. If you only use the hook API, the actual bundle impact is smaller than the full package size suggests.

## Caveats / Not Found

- Exact post-tree-shaking bundle sizes were not measured (would require a real build integration test)
- react-intl's ICU message format parser adds significant weight even with tree-shaking
- Custom solution does not handle edge cases like RTL, date/number formatting, or ICU plural rules (all out of scope per PRD)
- No benchmark of runtime performance differences (negligible for 20 strings in all cases)
