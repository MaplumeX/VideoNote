# feat: theme follows system mode

## Goal

让应用主题支持"跟随系统"模式，用户可以选择 light / dark / system 三种模式，选择 system 时实时响应操作系统主题变化。

## What I already know

* 当前 Theme 类型为 `"light" | "dark"`，没有 `system` 选项（`useTheme.tsx:3`）
* `getInitialTheme()` 已在 localStorage 无值时 fallback 到 `prefers-color-scheme`，但仅用于初始决定，没有运行时监听（`useTheme.tsx:8`）
* 主题切换按钮在 Sidebar 中，仅 toggle light/dark（`Sidebar.tsx:129-137, 171-178`）
* CSS 层面已完整支持 dark mode：`:root` + `.dark` CSS 变量、Tailwind `dark:` variant
* i18n 仅有 `theme.light` / `theme.dark`，缺少 `theme.system`（`en.json:107-109`, `zh-CN.json:107-109`）
* ThemeProvider 包裹在 AppLayout 中，仅对已认证路由生效

## Assumptions (validated)

* "system" 模式需要在运行时监听 `matchMedia` 变化并实时响应
* 用户手动选择 light/dark 后应覆盖 system 设置（localStorage 优先级高于系统）
* UI 形式：点击 Sidebar 主题图标弹出下拉菜单，三个选项带当前选中勾

## Open Questions

(none — all resolved)

## Requirements

* Theme 类型扩展为 `"light" | "dark" | "system"`
* 选择 system 时，应用 `matchMedia("(prefers-color-scheme: dark)")` 监听器实时响应系统主题变化
* localStorage 存储 "system" 值，表示用户选择了跟随系统
* Sidebar 主题图标改为下拉菜单，三个选项（Light / Dark / System）带当前选中勾
* i18n 添加 `theme.system` 翻译

## Acceptance Criteria

* [x] 选择 system 后，应用主题随操作系统切换实时变化
* [x] 手动选择 light/dark 后，覆盖 system 行为
* [x] Sidebar 主题下拉菜单展示三种选项，当前选中项带勾
* [x] 中英文 i18n 完整

## Definition of Done

* Lint / typecheck green
* 手动验证：macOS 切换外观设置时应用实时跟随

## Out of Scope

* 登录/注册页面的主题（当前未包裹 ThemeProvider）
* Mermaid 图表在主题切换时的即时刷新

## Technical Approach

* `useTheme.tsx`：Theme 类型加 `"system"`；新增 `resolvedTheme`（实际应用到 DOM 的 light/dark）；`setTheme` 替代 `toggleTheme`；system 模式下用 `matchMedia` 监听器驱动 `resolvedTheme`；`matchMedia` 监听在 effect 中注册+清理
* `Sidebar.tsx`：主题图标改为 DropdownMenu 触发器，菜单项三个选项带 Check 图标
* i18n：en/zh-CN 添加 `theme.system` 键
