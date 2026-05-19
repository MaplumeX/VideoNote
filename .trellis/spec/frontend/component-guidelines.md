# Component Guidelines

> How components are built in this project.

---

## Component Structure

Named exports, no default exports. Props interface above the component.

```tsx
interface VideoInputProps {
  onSubmit: (data: { url?: string; file?: File }) => void;
  disabled?: boolean;
}

export function VideoInput({ onSubmit, disabled }: VideoInputProps) {
  // ...
}
```

---

## Styling Patterns

**Tailwind CSS only.** No CSS modules, no styled-components, no inline styles.

Use `cn()` for conditional class merging:

```tsx
import { cn } from "@/lib/utils";

<div className={cn("rounded-lg border p-4", isActive && "border-blue-500")} />
```

shadcn/ui components in `components/ui/` — install via CLI, don't hand-write. Available: `Button`, `Input`, `Select`, `Card`, `Badge`, `Separator`, `DropdownMenu`.

Use shadcn/ui components for all interactive elements:
- Buttons → `<Button variant="...">` (default, outline, ghost, destructive)
- Inputs → `<Input>` (replaces raw `<input>`)
- Selects → `<Select>/<SelectTrigger>/<SelectContent>/<SelectItem>` (replaces raw `<select>`)
- Cards → `<Card>/<CardHeader>/<CardTitle>/<CardContent>`
- Badges → `<Badge variant="...">` (default, secondary, destructive)

**Dark mode**: Toggle `document.documentElement.classList.toggle("dark")`. Use MutationObserver on `<html>` class attribute for reactive state.

---

## react-markdown with Custom Components

### Pattern: TimestampBadge for video timestamps

The LLM generates Markdown with `[HH:MM:SS](#t=SECONDS)` links. Override `a` component in react-markdown to render these as clickable badges:

```tsx
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

<Markdown
  remarkPlugins={[remarkGfm]}
  components={{
    a({ href, children }) {
      if (href?.startsWith("#t=")) {
        const seconds = parseInt(href.slice(3));
        return <TimestampBadge seconds={seconds}>{children}</TimestampBadge>;
      }
      return <a href={href}>{children}</a>;
    },
  }}
>
  {markdownContent}
</Markdown>
```

> **Warning**: Do NOT spread `...rest` from react-markdown's component props to native elements. react-markdown passes extra props (`node`, `index`, etc.) that are not valid HTML attributes and cause React warnings.

---

## Common Mistakes

### Don't: Call setState during render

```tsx
// BAD — causes infinite re-renders in StrictMode
function App() {
  if (progress?.stage === "complete") {
    setNoteMarkdown(progress.result); // called during render!
  }
}

// GOOD — use useEffect
useEffect(() => {
  if (progress?.stage === "complete") {
    setNoteMarkdown(progress.result);
  }
}, [progress?.stage, progress?.result]);
```

### Don't: Spread unknown props to native elements

```tsx
// BAD — react-markdown passes node, index, etc.
a({ node, href, children, ...rest }) {
  return <a href={href} {...rest}>{children}</a>; // React warning
}

// GOOD — only pass what's needed
a({ href, children }) {
  return <a href={href}>{children}</a>;
}
```
