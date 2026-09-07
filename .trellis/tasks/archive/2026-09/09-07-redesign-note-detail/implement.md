# 执行计划：重新设计笔记详情页

工作目录：`frontend/`（除非注明）。验证命令均在 `frontend/` 下执行。

## 前置检查

- [ ] 确认 shadcn 组件可用性：`components/ui/` 下现有 Tooltip、Sheet、DropdownMenu、Popover；缺 Popover 则用 `npx shadcn@latest add popover` 安装并检查 @base-ui 兼容（render prop）。
- [ ] 确认 `NewNotePage.test.tsx` 现有测试模式（测试框架、render 方式），供新测试参考。

## Step 1: 新建 NoteMetaPopover 组件

- [ ] `frontend/src/components/NoteMetaPopover.tsx`：迁移标签 chips/输入/建议 + 文件夹树选择，Popover 容器（外点/Esc 关闭由 @base-ui 提供）。
- [ ] Props 接口见 design.md；命名导出；样式遵循 Tailwind + CSS 变量模式（色点、深度缩进）。
- [ ] i18n：复用现有 `noteDetail.*` key，缺则新增（zh/en）。
- 验证：`npm run build` 通过；组件在页面暂未接入。

## Step 2: 新建 NoteDetailHeader 组件

- [ ] `frontend/src/components/NoteDetailHeader.tsx`：返回按钮、标题（line-clamp）、元信息行、保存状态指示、操作按钮组（收藏/播放/下载）、信息入口（内嵌 NoteMetaPopover）。
- [ ] `lg:` 断点下操作收进 DropdownMenu（Ellipsis）。
- [ ] Tooltip 注意 @base-ui `render` prop 用法（见 spec 警告）。
- 验证：`npm run build` 通过。

## Step 3: 改造 NoteDetailPage 布局

- [ ] 删除左侧 aside（含旧面包屑、旧 tag 输入、旧 folder picker、renderFolderNodes）。
- [ ] 组装：`NoteDetailHeader`（sticky top-0，含 TOC 开关按钮）+ 正文 `mx-auto max-w-3xl px-4` + 宽屏 `TableOfContents`（`hidden xl:block`）+ `NoteTocSheet`（`xl:hidden`）。
- [ ] 修正失败态：SSE failed/cancelled 时保留 processing 视图 + `VideoInfoCard` + 重试按钮（`processError` state 方案，见 design.md）。
- [ ] 保存状态 props 传入 Header（saving/saveError/hasUnsavedChanges）。
- 验证：`npm run build` 通过；`npm run dev` 手动走查 AC1–AC8。

## Step 4: 测试

- [ ] `NoteDetailPage.test.tsx`（或扩充现有测试文件）：
  - 头部渲染标题/操作按钮存在性（AC1/AC2）。
  - 文件夹选择器：打开 Popover → 外点/Esc 关闭（AC3）。
  - 标签添加/删除（AC3）。
- [ ] 回归：时间戳点击 → 播放器打开（AC8，如现有测试已有则跑通即可）。
- 验证：`npm test` 全绿。

## Step 5: 收尾

- [ ] `npm run lint`（如有）/ `npm run build` / `npm test` 全部通过。
- [ ] 检查无残留死代码、无未使用 import。
- [ ] 对照 PRD AC1–AC10 逐条自查并勾选。

## 风险文件与回滚点

| 文件 | 风险 | 回滚 |
|---|---|---|
| `NoteDetailPage.tsx` | 高——大量结构改动，但数据逻辑不动 | revert commit |
| `NoteMetaPopover.tsx` / `NoteDetailHeader.tsx` | 低——新文件 | 删除即可 |
| `i18n` locale 文件 | 低——纯增量 | revert |
| `NoteEditor.tsx` / `TableOfContents.tsx` | 应零改动；若被迫改动需在 check 阶段重点审查 | — |

## 分步 commit 建议

1. `feat(ui): add NoteMetaPopover component`
2. `feat(ui): add NoteDetailHeader component`
3. `refactor(ui): redesign note detail page layout`
4. `test(ui): cover note detail header interactions`

## task.py start 前检查

- [ ] prd.md 收敛（Open Questions 已解决：Q1=方案A，Q2=整合单入口）
- [ ] design.md / implement.md 完成
- [ ] implement.jsonl / check.jsonl 已有真实条目（非 _example）
