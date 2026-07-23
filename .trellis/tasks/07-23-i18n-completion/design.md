# Design: i18n 完善 — 前端硬编码修复 + 后端错误消息翻译机制

## 1. 后端错误码机制

### 方案：结构化错误响应

后端 `HTTPException(detail=...)` 当前返回 `{"detail": "Invalid credentials"}`（字符串）。改为返回错误码 + 参数对象：

```json
{ "detail": { "code": "INVALID_CREDENTIALS", "params": {} } }
```

带插值参数的示例（`Task {job_id} not found`）：

```json
{ "detail": { "code": "TASK_NOT_FOUND", "params": { "job_id": "abc123" } } }
```

### 选择理由（vs. 纯错误码字符串）

- 保留参数上下文，前端可按 `"errors.taskNotFound": "任务 {{jobId}} 未找到"` 插值。
- 向后兼容：前端检测 `detail` 是否为对象；旧字符串则降级为原样展示（过渡期安全）。
- FastAPI `HTTPException.detail` 原生支持任意 JSON-serializable 值（含对象），无需自定义异常类。

### 错误码清单（34 项）

命名规范：`SCREAMING_SNAKE_CASE`，按资源分组：

| 资源 | 错误码 | params |
|---|---|---|
| auth | `EMAIL_ALREADY_REGISTERED` | — |
| auth | `INVALID_CREDENTIALS` | — |
| auth | `NO_REFRESH_TOKEN` | — |
| auth | `INVALID_REFRESH_TOKEN` | — |
| auth | `REFRESH_TOKEN_EXPIRED` | — |
| auth | `TOKEN_REUSE_DETECTED` | — |
| auth | `USER_NOT_FOUND` | — |
| auth | `INVALID_TOKEN_PAYLOAD` | — |
| auth | `ACCESS_TOKEN_EXPIRED` | — |
| auth | `INVALID_ACCESS_TOKEN` | — |
| note | `TAG_NAME_ALREADY_EXISTS` | — |
| note | `TAG_NOT_FOUND` | — |
| note | `FOLDER_NOT_FOUND` | — |
| note | `PARENT_FOLDER_NOT_FOUND` | — |
| note | `TASK_NOT_FOUND` | — |
| note | `TASK_WITH_ID_NOT_FOUND` | `{jobId}` |
| note | `TAG_NOT_ASSOCIATED` | — |
| note | `NOTE_NO_CONTENT` | — |
| task | `INVALID_FILENAME` | — |
| task | `THUMBNAIL_NOT_FOUND` | — |
| task | `TASK_STILL_PROCESSING` | — |
| task | `ONLY_FAILED_CAN_RETRY` | — |
| task | `ONLY_URL_CAN_RETRY` | — |
| task | `TASK_ALREADY_FINISHED` | — |
| task | `TASK_FAILED` | `{message}` (透传内部 message) |
| upload | `UNSUPPORTED_VIDEO_PLATFORM` | — |
| upload | `UNSUPPORTED_FILE_TYPE` | `{contentType}` |
| upload | `FILE_TOO_LARGE` | `{maxMb}` |
| cookie | `COOKIE_TOO_LARGE` | — |
| cookie | `COOKIE_NO_FILE` | — |
| cookie | `COOKIE_NO_TEXT` | — |
| cookie | `UNSUPPORTED_CONTENT_TYPE` | — |
| cookie | `NO_VALID_COOKIE_ENTRIES` | `{platform}` |
| cookie | `UNSUPPORTED_PLATFORM` | `{platform}` |
| cookie | `NO_COOKIE_FOUND` | `{platform}` |

### 实现

在 `backend/app/errors.py` 新增辅助：

```python
def error_detail(code: str, **params) -> dict:
    return {"code": code, **({"params": params} if params else {})}
```

各路由 `detail="Invalid credentials"` → `detail=error_detail("INVALID_CREDENTIALS")`。

`_REUSE_MSG` 常量删除，直接用 `error_detail("TOKEN_REUSE_DETECTED")`。

## 2. 前端翻译层

### 2.1 API client 统一翻译

在 `frontend/src/api/client.ts` 新增 `translateError(detail, t)`：

```ts
function translateApiError(detail: unknown, t: TFunction): string {
  if (typeof detail === "object" && detail !== null && "code" in detail) {
    const { code, params = {} } = detail as { code: string; params?: Record<string, unknown> };
    const key = `errors.${snakeToCamel(code)}`;
    const fallback = t("errors.unknown");
    const translated = t(key, { ...params, default: fallback });
    return translated === key ? fallback : translated;
  }
  // 兼容降级：旧式字符串
  return typeof detail === "string" ? detail : t("errors.unknown");
}
```

`throw new Error(...)` 改为 `throw new Error(translateApiError(err.detail, t))`。

**问题**：`api/client.ts` 是普通函数，不在组件内，拿不到 `t`。两个选项：
- **A. 在 client.ts 内用 `i18n.t()`**（i18next 实例方法，非 hook），避免改函数签名。
- **B. 把原始 `detail` 透传给组件，组件内用 `t()` 翻译**。

**选 A**：i18next 单例已在 `i18n/index.ts` 导出，`api/client.ts` 直接 `import i18n` 并用 `i18n.t()`。语言切换时 i18next 自动响应，无需组件重渲染错误消息（登录页 actionData 场景除外，见 2.3）。

### 2.2 SSE 错误

`useSSE.ts` 的 4 处硬编码：
- `"Failed to connect to progress stream"` → `t("errors.sseConnectionFailed")`
- `data.message || "Processing failed"` → `data.message ? translateApiError(...) : t("errors.processingFailed")`
  - 注意：SSE `data.message` 可能是后端透传的处理错误（如 ffmpeg 失败），应经翻译层。
- `"Task cancelled"` → `t("errors.taskCancelled")`
- `"Connection to server lost"` → `t("errors.sseConnectionLost")`

`useSSE` 是 React hook，可直接用 `useTranslation()`。

### 2.3 登录/注册 actionData

`LoginPage.tsx` / `RegisterPage.tsx` 用 react-router `actionData`（非响应式）传递错误字符串。问题：登录失败后用户切换语言，actionData 中的英文错误不会刷新。

**方案**：`action` 函数返回错误**码**而非翻译字符串：

```ts
// LoginPage action
return { errorCode: data.detail?.code || "LOGIN_FAILED" };
// LoginPage 组件
const msg = actionData?.errorCode ? t(`errors.${snakeToCamel(actionData.errorCode)}`) : null;
```

### 2.4 其他透传点

- `useVideoUpload.ts:48` `detail = err.detail || detail` → 用 `translateApiError`。
- `ContentSidebar.tsx:86,98,110,122` `e.message` 已经是 `api/client.ts` 翻译后的字符串，保持现状即可（二次翻译会破坏）。
- `NoteDetailPage.tsx:83` `err.message === "Still processing"` 字符串比较 → 改为错误码判断（`err.code === "TASK_STILL_PROCESSING"`）。

## 3. Milkdown Slash 工具栏

`NoteEditor.tsx` 的 `slashItems` 是模块级常量，label/description 硬编码。改造为工厂函数：

```ts
function buildSlashItems(t: TFunction): SlashItem[] {
  return [
    { label: t("editor.heading1"), description: t("editor.heading1Desc"), icon: "H1", ... },
    ...
  ];
}
// 组件内
const { t } = useTranslation();
const items = useMemo(() => buildSlashItems(t), [t]);
```

约 16 条文本，新增 `editor` 命名空间。

## 4. shadcn UI 组件

- `ui/sheet.tsx:75` `<span className="sr-only">Close</span>` → `{t("common.close")}`
- `ui/pagination.tsx` Previous/Next/aria → `t("common.previous")` 等
- `ui/combobox.tsx:26` "No options found" → `t("common.noOptions")`

新增 `common` 命名空间。这些是通用组件，用 `useTranslation()` 在组件内调用即可。

## 5. 其他硬编码

- `VideoPlayerFloat.tsx:258,293` "Video Player" → `t("videoPlayer.title")`（键已存在）
- `VideoInfoCard.tsx:33` "Video thumbnail" → `t("videoInfo.thumbnail")`（键已存在）
- `milkdown-mermaid.ts:146` "Mermaid rendering failed" → `t("mermaid.renderFailed")`（键已存在）

`milkdown-mermaid.ts` 非组件，用 `i18n.t()`。

## 6. 语言资源扩展

`zh-CN.json` / `en.json` 新增：
- `errors`：34 个错误码键 + `unknown`、`sseConnectionFailed`、`sseConnectionLost`、`taskCancelled`、`processingFailed`、`loginFailed` 等。
- `common`：`close`、`previous`、`next`、`goToPreviousPage`、`goToNextPage`、`noOptions`。
- `editor`：16 个 slash 工具栏文本。

## 7. 兼容性

- 后端 `detail` 改为对象，前端 `translateApiError` 兼容旧字符串（降级原样展示）。过渡期安全。
- HTTP 状态码不变。
- 前端构建（tsc + vite）必须通过。

## 8. 验证策略

- 手动测试：中文环境登录失败、注册冲突、访问不存在任务、文件夹操作错误。
- 构建校验：`cd frontend && npm run build`。
- 键对称校验：脚本对比 en/zh-CN 键集。
- 硬编码扫描：复用本次扫描的 grep 正则。