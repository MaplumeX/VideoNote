# 技术设计：重新设计笔记详情页

## 总体方案

将「左侧固定操作栏 + 正文 + TOC」三栏布局重构为「Sticky 头部区 + 阅读优先正文 + 宽屏 TOC」结构。视觉风格沿用现有 shadcn 主题，只做布局与信息架构重构（用户决策：方案 A）。

```
┌──────────────────────────────────────────────────────┐
│ Header (sticky): ← 返回 | 标题+元信息 | 保存状态 · 操作区 │
│                    (信息入口 Popover: 标签+文件夹)        │
├──────────────────────────────────────────┬───────────┤
│                                          │   TOC     │
│   正文 (max-w-3xl mx-auto, Milkdown)      │  (≥xl)    │
│                                          │           │
└──────────────────────────────────────────┴───────────┘
窄屏(<xl): TOC 收进 Sheet；<lg: 操作收进 DropdownMenu
```

## 组件边界与拆分

现状问题：`NoteDetailPage.tsx` 约 530 行，UI 与数据逻辑混杂。本次拆分为：

| 新组件 | 职责 | 关键 Props |
|---|---|---|
| `NoteDetailHeader` | sticky 头部：返回、标题、元信息、保存状态、操作区、信息入口 | `title, platform, fileName, createdAt, saving, saveError, hasUnsavedChanges, isFavorite, onToggleFavorite, onDownload, onPlayVideo?, tags, folders...` |
| `NoteMetaPopover` | 「笔记信息」Popover：标签管理（chips + 输入 + 建议）+ 文件夹树选择 | `noteTags, allTags, folderTree, folderId, onAddTag, onRemoveTag, onMoveToFolder` |
| `NoteTocSheet` | 窄屏 TOC 抽屉（Sheet 包裹现有 `TableOfContents`） | `containerRef, contentKey, open, onOpenChange` |

`NoteDetailPage` 保留：数据获取（fetchResult/fetchTaskById/SSE/自动保存）与状态编排，布局组装。目标 <300 行。

`TableOfContents`、`NoteEditor`、`VideoPlayerFloat`、`StepIndicator` 不改内部逻辑（`TableOfContents` 仅在窄屏被 Sheet 复用，其自身查询 h2/h3 的逻辑不变）。

## 交互细节设计

### 头部区（NoteDetailHeader）

- 左：返回按钮（图标 `ArrowLeft`，回 `/app/history`）。
- 中：标题（`text-xl font-semibold`，长标题 `line-clamp` 收敛为两行内）+ 元信息行（平台徽章 / 文件名 / 创建时间，按现有数据有则显示）。
- 右：保存状态指示（图标 + 文字：`Loader2` 旋转=保存中、`Check`=已保存、`TriangleAlert`=失败）+ 图标按钮组（收藏 `Star`、播放 `Play`（有视频时）、下载 `Download`、更多 `Ellipsis`）。
- 收藏反馈：`fill-current text-yellow-500`（沿用现有配色）。
- Tooltip 用现有 shadcn Tooltip（注意 @base-ui 的 `render` prop）。

### 信息入口（NoteMetaPopover）

- 触发按钮：`Tag` 图标 + 标签数徽标（如 `Tag 3`）。
- Popover 内容（`w-80`）分两节：
  - 标签：现有 chips 渲染逻辑迁移（色点 + 名称 + X 删除）、虚线添加按钮、输入 + 建议。键盘导航降级为现有行为（Enter 确认 / Esc 关输入），不实现上下键选择（成本考虑，PRD 已允许降级）。
  - 文件夹：`Select` 样式的树选择（沿用现有 `renderFolderNodes` 递归渲染 + 深度缩进 CSS 变量模式），选中项高亮。
- Popover 自带外点关闭/Esc 关闭（@base-ui 提供），满足 AC3。
- 现有手写 folder picker 的「无外点关闭」问题随之消除（旧代码删除）。

### 正文与 TOC

- 正文容器：`mx-auto w-full max-w-3xl px-4`（Milkdown 内容阅读宽度）。
- 宽屏（`xl:`）：`TableOfContents` 以 `w-56 shrink-0` 出现在正文右侧（页面级 `hidden xl:block`）。
- 窄屏：头部放一个 `ListTree` 图标按钮触发 `NoteTocSheet`（`xl:hidden`），Sheet 内复用 `TableOfContents`，点击条目后关闭 Sheet。

### 响应式断点

- `<lg`：头部操作区仅保留返回 + 标题 + 保存状态 + `Ellipsis` DropdownMenu（内含收藏/下载/播放/信息）。
- `≥lg`：全部图标按钮平铺。
- `<xl`：TOC 走 Sheet。
- 用 375px 与 768px 手动验证无横向滚动（AC5）。

### 处理中 / 失败态

- processing 视图保持现有 StepIndicator + 取消/重试按钮结构，`max-w-lg mx-auto` 居中不变。
- 修正：SSE failed 时不再走 `setError`（当前会切到纯 error 分支丢上下文），改为在 processing 视图内渲染错误信息 + 重试按钮 + 保留 `VideoInfoCard`。逻辑：新增局部 `processError` state，失败/取消时置入，处理视图据此显示。

## 数据流与兼容

- 所有 API 调用、hooks（`useSSE`、`useNoteAutoSave`）、路由不变。
- 头部所需元信息全部来自现有 `fetchTaskById`（TaskItem 已含 created_at/platform/file_name），无后端改动。
- `handleTimestampClick` → `VideoPlayerFloat` 链路不动。
- 旧左侧栏代码、旧手写 tag 输入/folder picker 全部删除，不留死代码。

## 权衡与取舍

- **标签键盘上下选择**：降级为现有 Enter/Esc 行为，避免重写手写下拉（若用 shadcn Command 组件成本高、且与色点样式耦合）。已在 PRD 允许降级。
- **TOC 双形态**（宽屏侧栏 + 窄屏 Sheet）复用同一 `TableOfContents`，代价是两处实例各跑一个 IntersectionObserver——可接受（窄屏时宽屏实例 display:none，observer 空转无视觉影响；如发现滚动高亮异常，窄屏实例用条件渲染 `open && <TableOfContents/>` 兜底）。
- **不改 AppLayout**：全局侧栏与页面头部并存，返回按钮目标是历史页（与现面包屑一致）。

## 回滚

单分支单 commit 粒度（或按 implement.md 分步 commit），出问题 revert 即可；无数据迁移、无 API 契约变更。
