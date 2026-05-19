# Polish Frontend UI

## Goal

对前端进行视觉打磨和组件升级，从"功能可用"提升到"精致软件"的水准——引入 shadcn/ui 统一设计语言，修复布局问题，美化各页面，支持暗色模式。

## Decisions

1. **引入 shadcn/ui** — 统一 Button、Input、Select、Card、Badge 等组件设计语言，暗色模式开箱即用
2. **暗色模式纳入 MVP** — 迁移过程本身就碰所有组件，顺手做最高效
3. **侧边栏 fixed + 内容区独立滚动** — 经典软件布局，侧边栏完全固定在视口，内容区域 `h-screen overflow-y-auto` 独立滚动

## Requirements

### 布局
- 侧边栏桌面端撑满视窗全高，fixed 定位
- 内容区域 h-screen + overflow-y-auto 独立滚动
- 统一各页面内容宽度策略（Dashboard/History 满宽，NewNote/Settings 居中限宽，NoteDetail 满宽）

### shadcn/ui 迁移
- 初始化 shadcn/ui（Tailwind v4 兼容）
- 引入组件：Button、Input、Select、Card、Badge、Separator、DropdownMenu
- 用 shadcn/ui 组件替换各页面的手写元素

### 代码整理
- StatusBadge 提取为共享组件（消除 Dashboard + History 重复定义）
- 按钮统一走 shadcn/ui Button（variant 区分）
- 消除 SettingsPage select 的内联 SVG 箭头 hack

### 视觉美化
- 卡片增加阴影/层次感
- 空状态 / 加载状态美化
- 整体间距、圆角统一

### 暗色模式
- 配置 Tailwind dark mode（class strategy）
- 侧边栏底部加主题切换按钮（与语言切换并列）
- 各页面暗色适配

## Acceptance Criteria

- [ ] 侧边栏桌面端固定全高，内容区独立滚动
- [ ] shadcn/ui 初始化成功，Button/Input/Select/Card/Badge 可用
- [ ] StatusBadge 只有一份定义
- [ ] 所有按钮走 shadcn/ui Button
- [ ] Settings select 走 shadcn/ui Select
- [ ] 暗色模式可切换，各页面两套主题视觉正常
- [ ] 桌面端 + 移动端视觉正常
- [ ] Lint / typecheck 通过

## Definition of Done

* Lint / typecheck 通过
* 桌面端 + 移动端 + 亮色/暗色 四种组合视觉正常
* shadcn/ui 组件库可用

## Out of Scope

* 新功能开发（如搜索、折叠侧边栏）
* 后端改动
* 认证页面（Login/Register）美化

## Technical Notes

* Sidebar.tsx:53 — `h-full` + `md:static` 在 `min-h-screen` 下不生效 → 改为 fixed + h-screen
* AppLayout.tsx:13 — 父容器 `min-h-screen flex` → 改为 `h-screen`，内容区 `overflow-y-auto`
* DashboardPage.tsx + HistoryPage.tsx 各定义 StatusBadge → 提取到 components/StatusBadge.tsx
* SettingsPage select 内联 SVG 箭头 → shadcn/ui Select 替换
* 按钮圆角不一致：Dashboard rounded-xl vs 其余 rounded-lg → shadcn/ui Button 统一
