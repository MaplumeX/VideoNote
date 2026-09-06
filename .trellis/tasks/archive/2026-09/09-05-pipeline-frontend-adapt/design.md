# 技术设计：C5 前端契约适配

> 依赖 C4 已落地的新 REST/SSE 契约（`docs/pipeline-contract.md` §2.4 变更表是唯一实施依据）。后端已冻结，前端切换。

## 1. 类型层（`types/index.ts`）

```typescript
export type TaskStatus = "pending" | "running" | "complete" | "failed" | "cancelled";
export type TaskPhase = "fetching" | "subtitle" | "audio" | "transcribe" | "notegen";

export interface TaskProgress {          // SSE progress 事件载荷（契约 §2.1）
  status: TaskStatus;
  phase: TaskPhase | null;
  phase_progress: number;                // ∈ [0,1] 阶段内
  message: string;
  attempt: number;                       // 1-based
  timestamp: string;                     // ISO 8601
}

export interface TaskItem {              // 列表/详情（契约 §2.4：stage → status + phase + phase_progress）
  job_id: string;
  status: TaskStatus;
  phase: TaskPhase | null;
  phase_progress: number;
  message: string;
  created_at: string;
  title: string | null;
  ... // 其余字段不变
}
```

删除旧 `TaskStage` 联合类型。`TaskItem.stage` 引用点全部迁移到 `status`/`phase`。

## 2. UI 映射设计（核心决策：进度条合成）

契约废除全局百分比。前端需要总进度时合成：`(phase_index + phase_progress) / phase_count`（契约 §2 明示公式）。

- **`StepIndicator.tsx`**：三步指示器保留（下载→转录→生成笔记），由 `phase` 推导步骤状态：
  - `fetching|subtitle|audio` → step1 active（`phase_progress` 作为 step1 内进度）
  - `transcribe` → step2 active；`notegen` → step3 active
  - failed/cancelled 只标红当前及其后步骤（历史修复语义保留：需要知道失败时的 phase——`TaskItem.phase` 终态为 null，但 SSE 流期间最后收到的 phase 有值；列表页无 phase 的终态行整行标红即可，与旧版对终态的处理一致）
  - URL/上传两种 source 的步骤差异保留（上传无 step1「下载」）
- **`ProgressBar.tsx`**：输入改为 `(phase, phase_progress)`，内部按路径合成总百分比；`subtitle` 命中跳级时合成公式自然跳到 notegen 段，无需特判。
- **`StatusBadge.tsx`**：`ACTIVE_STAGES.includes(stage)` → `status === "running"`；complete/failed/cancelled 分支读 `status`。
- **`NewNotePage.tsx`**：`progress?.stage === "failed"` 等改 `progress?.status`；消息实时展示逻辑保留。

## 3. `useSSE.ts` / `sseParser.ts`

- 解析逻辑不变（sseParser 与载荷结构无关，测试保留）。
- `TaskProgress` 类型跟随新载荷；`stageRef` 删或改 `phaseRef`（若仅用于终止判断，改用 `status`）。
- 断线重连/心跳/终态 complete 事件处理不变。
- `useSSE.test.ts` 更新 mock 载荷为新 schema。

## 4. 错误码与 i18n

- `TASK_MESSAGE_ERROR_CODES` 增补新码：`SUBTITLE_EXTRACTION_FAILED`（C1 新增）、`TASK_CANCELLED`（C4 取消终态码，会出现在 message）；`FETCHING_VIDEO_INFO` 等既有码保留。
- `STAGE_KEY`/状态文案：`progress.*` i18n key 按新 phase 重写（en/zh-CN）：fetching→「获取视频信息」、subtitle→「提取字幕」、audio→「下载音频」、transcribe→「转录音频」、notegen→「生成笔记」；status 文案沿用。
- 删除旧 stage key（`progress.downloading` 等）前先 grep 确认零引用。

## 5. 页面级迁移

- `DashboardPage.tsx` / `HistoryPage.tsx` / `NoteDetailPage.tsx`：`task.stage === "complete"` → `task.status === "complete"` 等；显示用 `task.stage` 的地方（423 行 fallback）改显示翻译后的 status。
- `useVideoUpload.ts`：不涉及 stage（仅 job_id/语言），预计零改动；测试确认。

## 6. 测试设计

- `StepIndicator.test.ts`：新 phase → 步骤状态矩阵（含 subtitle 命中、上传路径、failed 标红范围）。
- `useSSE.test.ts`：新载荷 schema 的解析/终态/重连。
- `NewNotePage.test.tsx`：进度渲染 smoke。
- `api/client.test.ts`：translateTaskMessage 新码。
- 手动验收：npm run build 通过。

## 7. 边界

- 不改后端任何文件；不改 sseParser 核心解析；不碰编辑器/笔记管理/设置页（类型引用连带最小调整除外）。
- 双语 i18n 无缺 key（tsc + 手查）。
