# PRD: i18n 完善 — 前端硬编码修复 + 后端错误消息翻译机制

## 背景

项目当前已具备 i18n 基础设施（i18next + react-i18next，en/zh-CN 双语言，181 个键完全对齐），组件层面 `useTranslation()` 覆盖良好。但存在系统性缺口：

1. **后端错误消息硬编码英文**：`HTTPException(detail="Invalid credentials")` 等字符串原样透传到前端 `data.detail`，前端无法翻译。
2. **前端多处硬编码字符串**未走 `t()`：登录/注册错误、SSE 错误、API client 抛错、Milkdown 编辑器工具栏、shadcn UI 组件（sheet/pagination/combobox）等。
3. **错误透传链路**：`api/client.ts` 把 `err.detail` 直接 `throw new Error(err.detail)`，消费方 `e.message` 直接展示，绕过翻译层。

## 目标

完善 i18n 体系，使用户可见的所有文本（含错误消息）都能按当前语言正确显示。

## 范围

### In Scope

**A. 后端错误消息错误码机制**
- 后端 `HTTPException(detail=...)` 改为返回结构化错误码：`detail` 字段返回机器可读的错误码（如 `INVALID_CREDENTIALS`），附加可选参数（如 `{{field}}`、`{{max}}`）用于插值。
- 涉及文件：`backend/app/api/auth_routes.py`、`note_routes.py`、`routes.py`、`cookie_routes.py`、`auth.py`。
- 保持 HTTP 状态码不变；仅把 `detail` 字符串改为错误码 + 参数对象。

**B. 前端错误码 → 翻译键映射**
- 在 `api/client.ts` 统一把后端返回的 `detail`（错误码 + 参数）翻译为本地化字符串，再向上抛出。
- 前端语言资源扩展：新增 `errors` 命名空间，覆盖所有后端错误码。
- 修复链路：`api/client.ts`、`useSSE.ts`、`useVideoUpload.ts` 的错误透传点。

**C. 前端硬编码字符串清理**
- 登录/注册页：`LoginPage.tsx`、`RegisterPage.tsx` 错误消息。
- SSE hook：`useSSE.ts` 的 4 处硬编码错误字符串。
- Milkdown 编辑器工具栏：`NoteEditor.tsx` 中约 16 条硬编码英文（heading/list/quote/table/divider 等）。
- shadcn UI 组件：`ui/sheet.tsx`（Close）、`ui/pagination.tsx`（Previous/Next）、`ui/combobox.tsx`（No options found）。
- `VideoPlayerFloat.tsx`、`VideoInfoCard.tsx`、`milkdown-mermaid.ts` 等。

### Out of Scope（豁免）

- **语言自名称**：`SettingsPage.tsx` 的 `LANG_LABELS`（"English"/"中文"）—— 业内惯例用各自母语展示，保留硬编码。
- **平台/品牌名**：YouTube、Bilibili、NoteSlash、Mermaid 等专有名词。
- **键盘键名比较**：`e.key === "Enter"`、`"Escape"`、`"ArrowDown"` 等作为逻辑判断的字符串字面量，非用户可见文本。
- **后端内部异常**：`ValueError`、`RuntimeError`（如 ffmpeg 失败）属于开发者诊断信息，不纳入用户可见翻译范围；但其最终透传到前端的 message 仍需考虑（见验收标准 4）。

## 验收标准

1. **双语言完整**：`en.json` 与 `zh-CN.json` 键全对齐，新增 `errors` 命名空间覆盖所有后端错误码，无非对称键。
2. **零硬编码**：除豁免清单外，`frontend/src/**/*.{ts,tsx}` 中不存在用户可见的硬编码字符串（登错误、toast、UI 标签、占位符、sr-only 等）。
3. **错误消息本地化**：在中文环境下，登录失败、注册冲突、任务不存在、文件夹不存在、Cookie 上传错误等所有后端错误，前端均显示中文。
4. **进度流错误**：`useSSE.ts` 的连接失败、处理失败、取消、断连四类消息按当前语言显示。
5. **切换语言无白屏**：登录页存在 actionData 错误时切换语言，错误消息跟随切换。
6. **不引入破坏性**：HTTP API 状态码、请求/响应结构（除 `detail` 字段内容形式外）不变；前端构建通过。

## 风险与权衡

- **错误码方案选择**：后端 `detail` 改为 `{ "code": "INVALID_CREDENTIALS", "params": {..} }` vs. 纯错误码字符串 `"INVALID_CREDENTIALS"`。前者支持插值参数（如 `Task {{job_id}} not found`），后者更简单但丢失上下文。详见 design.md。
- **前端翻译层位置**：集中在 `api/client.ts` 统一处理 vs. 各消费方组件分散翻译。集中化更易维护，但需处理 `useSSE.ts` 等非 HTTP 错误路径。
- **Milkdown 工具栏**：检查 Milkdown 是否原生支持 i18n 配置，避免硬改组件源码。