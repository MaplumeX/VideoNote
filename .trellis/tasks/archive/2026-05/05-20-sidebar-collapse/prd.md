# Sidebar Collapse

## Goal

为主应用导航侧边栏添加桌面端折叠功能，折叠后以图标模式显示（~56px），让用户获得更大的内容区域。

## Requirements

* 桌面端侧边栏支持折叠为图标模式，展开时宽度 w-52（208px），折叠时宽度 ~56px
* 折叠后仅显示图标，hover 显示 tooltip（使用 Shadcn Tooltip 组件）
* 折叠按钮位于侧边栏底部区域
* 支持 `Cmd+B`（Mac）/ `Ctrl+B`（Windows）快捷键切换
* 折叠状态持久化到 localStorage，刷新后保持
* 展开/折叠过渡动画流畅（width + margin-left 同步过渡）
* 主内容区左侧偏移量随侧边栏宽度变化
* 移动端行为不变（仍使用 slide-in overlay 模式）

## Acceptance Criteria

* [ ] 点击折叠按钮可切换侧边栏展开/收起
* [ ] `Cmd/Ctrl+B` 快捷键可切换
* [ ] 折叠后仅显示图标，hover 显示 tooltip 标签文字
* [ ] 主内容区左侧偏移量随侧边栏宽度自动调整
* [ ] 折叠状态刷新后保持（localStorage）
* [ ] 展开/折叠过渡动画流畅
* [ ] 移动端行为不变

## Definition of Done

* Lint / typecheck 通过
* 手动验证桌面端和移动端表现

## Decision (ADR-lite)

**Context**: 需要决定折叠后的显示模式
**Decision**: 图标模式（缩窄为 ~56px，仅图标 + tooltip），而非完全隐藏或 overlay
**Consequences**: 常用导航可直接点击，视觉连续性好；需实现 tooltip 支持

**Context**: 折叠状态是否持久化
**Decision**: 是，存 localStorage
**Consequences**: 用户偏好跨会话保持

**Context**: 是否支持快捷键
**Decision**: 是，Cmd/Ctrl+B
**Consequences**: 符合常见 IDE 习惯

## Out of Scope

* ContentSidebar（HistoryPage 的筛选侧边栏）
* NoteDetailPage 的 aside 侧边栏
* 侧边栏可拖拽调整宽度
* 侧边栏面板/二级导航

## Technical Notes

* 关键文件：`Sidebar.tsx`, `AppLayout.tsx`, `index.css`
* 侧边栏是 fixed 定位 + 主内容 margin-left 偏移，需要在两个组件间同步宽度状态
* 当前移动端使用 `translate-x` 动画，桌面端用 `md:translate-x-0` 强制显示
* 折叠状态管理：在 AppLayout 中用 useState + localStorage 初始值，通过 props 传给 Sidebar
* Shadcn Tooltip 组件已有 @base-ui/react 依赖，可直接使用
* 过渡动画：sidebar width + content margin-left 都需要 transition
