# Implement: i18n 完善

## 执行清单

### Phase A: 后端错误码机制

- [x] **A1** 新建 `backend/app/errors.py`，导出 `error_detail(code, **params)` 辅助函数。
- [x] **A2** `auth_routes.py`：替换 8 处 `detail="..."` → `error_detail(...)`（含 `_REUSE_MSG` 常量删除）。
- [x] **A3** `note_routes.py`：替换所有 `detail="..."`（Tag/Folder/Task 系列，含 f-string `Task {job_id} not found` → `error_detail("TASK_WITH_ID_NOT_FOUND", jobId=job_id)`）。
- [x] **A4** `routes.py`：替换所有 `detail="..."`（任务/上传/缩略图系列，含 f-string插值）。
- [x] **A5** `cookie_routes.py`：替换所有 `detail="..."`（含多行 f-string）。
- [x] **A6** `auth.py`：替换 3 处 token 相关 detail。
- [x] **A7** 运行后端测试 `pytest backend/tests/`，确认未破坏（6 passed）。

### Phase B: 前端语言资源扩展

- [x] **B1** `zh-CN.json` 新增 `errors` 命名空间（34 错误码 + unknown/sseConnectionFailed/sseConnectionLost/taskCancelled/processingFailed/loginFailed/registrationFailed）。
- [x] **B2** `en.json` 同步新增对应键。
- [x] **B3** 新增 `common` 命名空间（close/previous/next/goToPreviousPage/goToNextPage/noOptions/loading）。
- [x] **B4** 新增 `editor` 命名空间（10 个 slash 工具栏 label + description）。
- [x] **B5** 脚本校验 en/zh-CN 键完全对称（251 键）。

### Phase C: 前端翻译层

- [x] **C1** `api/client.ts`：新增 `translateApiError(detail)` 函数 + `snakeToCamel` + `ApiError` 类 + `extractCode`，用 `i18n.t()` 实例方法；`apiFetch`、`fetchResult`、`saveSettings` 三处抛错改为翻译后抛出。
- [x] **C2** `useSSE.ts`：引入 `useTranslation`，4 处硬编码字符串改 `t(...)`。
- [x] **C3** `useVideoUpload.ts:48` `detail = err.detail || detail` 改为 `translateApiError`。
- [x] **C4** `LoginPage.tsx`：action 返回 `errorDetail`，组件用 `translateApiError()` 翻译；删除 "Invalid credentials"/"Login failed" 硬编码。
- [x] **C5** `RegisterPage.tsx`：同 C4 模式。
- [x] **C6** `NoteDetailPage.tsx:83` 字符串比较 `err.message === "Still processing"` 改为 `ApiError` + code 判定。

### Phase D: 前端硬编码清理

- [x] **D1** `NoteEditor.tsx`：`slashItems` 模块常量改为 `buildSlashItems(t)` 工厂函数，组件内 `useMemo` 调用。
- [x] **D2** `ui/sheet.tsx:75` "Close" → `t("common.close")`（已加 `useTranslation`）。
- [x] **D3** `ui/pagination.tsx` 4 处文本 → `t("common.*")`（已加 `useTranslation`）。
- [x] **D4** `ui/combobox.tsx:26` "No options found" → `t("common.noOptions")`（已加 `useTranslation`）。
- [x] **D5** `VideoPlayerFloat.tsx:258,293` — 已使用 `t("videoPlayer.title", "Video Player")` 无需改动。
- [x] **D6** `VideoInfoCard.tsx:33` "Video thumbnail" → `t("videoInfo.thumbnail")`。
- [x] **D7** `milkdown-mermaid.ts:146` "Mermaid rendering failed" → `i18n.t("mermaid.error")`。

### Phase E: 验证

- [x] **E1** `cd frontend && npm run build`（tsc + vite）通过。
- [x] **E2** 复用扫描正则，确认豁免清单外无硬编码残留。
- [x] **E3** 中文硬编码仅剩 `SettingsPage.tsx` 的 `中文`（语言自名称，豁免）。
- [x] **E4** 键对称校验脚本：en/zh-CN 键集相等（251 = 251）。