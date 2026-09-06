# 技术设计：C4 流水线编排器与 API 层

> 本任务是新旧链路切换点。依赖 C1（状态机/持久层/契约）与 C2/C3（五个阶段模块）已交付并冻结。

## 1. 模块布局

```
backend/app/pipeline/
├── orchestrator.py       # 状态机驱动的执行器（本任务核心）
├── context.py            # RuntimeStageContext 组装（DB artifact store、进度发布、取消句柄注册表）
└── runner.py             # PipelineTaskRunner：调度 + asyncio 原生取消（替代 task_runner.py 的取消职责）
backend/app/api/
└── routes.py             # 瘦身：只留鉴权/校验/HTTP 映射，编排委托 orchestrator
```

删除（切换完成后）：`app/task_runner.py`、`app/services/{subtitle,audio,transcribe,note_gen}.py` 及其旧测试；`services/markdown.py` 迁移为 `pipeline/markdown.py`（notegen 唯一依赖方）。

## 2. orchestrator.py 设计

### 2.1 核心结构

```python
class Orchestrator:
    def __init__(self): 
        self._cancel_handles: dict[str, CancelHandleRegistrar] = {}   # job_id -> registrar
        self._running: set[str] = {}

    async def run(self, job_id: str, plan: ExecutionPlan) -> None: ...
    def cancel(self, job_id: str) -> bool: ...        # 触发当前阶段句柄 + asyncio task cancel
```

`ExecutionPlan`：`job_id`、`source_type`（url/upload）、`url | input_path`、`language`、`provider: ProviderConfig`、`path: list[PipelinePhase]`（URL_PATH/FILE_PATH）。

### 2.2 主循环（状态机驱动）

```python
async def run(self, job_id, plan):
    cp = await read_checkpoint(job_id)
    phase = resume_point(plan.path, parse_checkpoint(cp))
    attempt = cp["attempt_count"]
    while phase is not None:
        await save_checkpoint_phase(...)                     # 进度：status=running, phase=phase, progress=0
        stage = STAGES[phase]
        ctx = build_stage_context(job_id, plan, self._registry_for(job_id))
        try:
            result = await stage.run(ctx, resume=phase_was_resumed)
        except PipelineError as e:  -> 终态 failed(e.code, e.detail); return
        except asyncio.CancelledError: -> 终态 cancelled; return   # 编排器负责落库终态
        # 产物落库 + 检查点推进
        for kind, content in result.outputs.items(): await save_artifact(job_id, kind, content)
        await save_checkpoint(job_id, phase)                  # 条件写：cancelled 赢
        # extra 合并进 plan（audio_path / notes 传递）
        phase = advance(plan.path, phase, artifacts_present)  # subtitle 命中 → notegen；notegen 完成 → None
    # 完成：notes 写 result_json + status=complete（条件写）
```

要点：
- **终态写入幂等**（C1 检查的备忘）：failed/cancelled/complete 写入用条件 UPDATE（`WHERE status NOT IN terminal AND cancel_requested=0`），重复写不影响。
- **notegen 的 notes 经 extra 传递**：主循环结束后从累计 extra 取 `notes` 写 `result_json`；`video_meta` 的 title/thumbnail 同步写 tasks 行（`update_task_meta` 语义迁移）。
- **上传文件清理**：终态（complete/cancelled/failed）后删除 input_file_path + 清 WAV（`tmp/videonote_pipeline_audio/{job_id}.wav`，C2 备案的清理责任）+ 清理 per-user cookie 临时文件。
- **取消感知双通道**：`request_task_cancel` 落库意图（既有 DB 函数）→ 编排器在阶段 await 期间由 runner 触发 asyncio cancel；阶段内部句柄（子进程 kill）由 `register_cancel` 联动。DB 意图写入与内存取消之间竞态由条件写兜底（谁先到都收敛到 cancelled）。

### 2.3 STAGES 注册表

`{fetching: FetchStage, subtitle: SubtitleStage, audio: AudioStage, transcribe: TranscribeStage, notegen: NoteGenStage}`，均无状态单例。

### 2.4 恢复与尝试上限

- 启动恢复（改造 `recover_incomplete_tasks`，迁入 orchestrator 模块或由其提供 `recover()`）：`get_recoverable_tasks()` 逐个判断 attempt 上限（`TASK_RECOVERY_MAX_ATTEMPTS` 语义保留）→ 构造 ExecutionPlan → `schedule`。
- 用户 retry：仅 failed/cancelled 可 retry（既有 409 语义）；retry 重置 `cancel_requested=0`、`attempt_count+1`、从检查点恢复（有 transcript 产物则跳过转录，直接 notegen——父任务 R2 验收）。
- 旧链路遗留的非终态任务（无 checkpoint）：`resume_point` 返回路径首阶段，从头执行（C1 已定义语义）。

## 3. runner.py 设计（替代 task_runner.py）

保留：`schedule(job_id, coro_factory) -> bool` 防重复调度（dict[str, asyncio.Task] + done_callback 清理）、`is_running`、`shutdown`。
变更：factory 签名从 `Callable[[threading.Event], Awaitable]` 改为 `Callable[[], Awaitable]`；cancel 改为 `task.cancel()` + 等待清理（`asyncio.gather(..., return_exceptions=True)`）；`shutdown` 不再设 threading.Event。增量 attempt 语义（旧 `_run` 里 `increment_attempt`）迁到编排器调度入口。

## 4. routes.py 瘦身

**保留端点与职责**（路径不变，载荷按新契约）：`/process`、`/upload`、`/tasks/{id}/progress`（SSE 载荷换 ProgressEvent schema）、`/result`、`/tasks`、`/tasks/{id}`、`DELETE /tasks/{id}`、`/retry`（检查点恢复语义）、`/cancel`、`/thumbnails/{filename}`、`/models`、`/providers`、`/settings`、上传安全（`_sanitize_upload_name`/类型白名单/大小限制）、`_get_user_cookiefile`/`_get_user_provider`/`_resolve_providers`（改返回 ProviderConfig）。

**删除**：`_process_video_url`、`_process_video_file`、`_to_thread_with_cancel`、`_cancellation_checkpoint`、`_StageFailed`、`ProviderBundle`（被 ProviderConfig 取代）、`_make_asr_progress_cb`/`_make_note_progress_cb`、`_subtitle_languages`/`_asr_language`（已在 C2 stage 内）、`_sanitize_error_detail`（已在 pipeline/errors.py）。

**SSE 端点改造**：轮询读 `status/phase/phase_progress/message`（新列）+ 心跳 + 终态附 `complete` 事件（结构保留）；30 分钟上限保留。

**恢复调用点**：`main.py` lifespan 中 `recover_incomplete_tasks` 改调编排器版本；`task_runner` 引用全部换 `pipeline.runner`。

**目标行数** ≤ ~450 行（现 1250）。

## 5. 契约不变量（不得违反）

- ProgressEvent SSE 载荷字段与 docs/pipeline-contract.md 完全一致；phase 单调（状态机保证）+ phase_progress 单调（tracker 保证）。
- 阶段间只通过 artifacts + extra 传递数据；编排器是唯一 DB 写入方（阶段不写）。
- 破坏性变更集中本任务：`TaskListItem`/`TaskProgress` 等响应模型换新枚举（status+phase），旧 `stage` 列停止写入但保留（历史任务展示仍读旧列，回填映射展示——列表页对旧行用旧值、新行用新值，`COALESCE` 风格处理）。

## 6. 测试设计（tests/pipeline/，全部无外网）

- `test_orchestrator.py`：假 stage 注册表注入编排器——三路径推进、subtitle 命中跳级、PipelineError→failed、CancelledError→cancelled、检查点推进断言、终态幂等重写、attempt 上限、retry 从检查点恢复（断言不重跑已完成阶段）、extra 传递（audio_path→transcribe、notes→result_json）。
- `test_runner.py`：防重复调度、cancel 清理、shutdown。
- `test_routes_pipeline.py`（TestClient）：/process 创建任务并调度（假 stage）、SSE 载荷 schema 断言、/retry 语义、/cancel ≤3s（假 stage await sleep 可中断）、/result、鉴权 404/权限、上传安全保留。
- `test_recovery.py`：重启恢复矩阵（可恢复 URL/上传、attempt 超限、无效输入、不支持 URL——对照 spec Durable 契约的 Validation & Error Matrix）。
- 旧测试处理：`test_core_reliability`/`test_pipeline_*`/`test_audio_download`/`test_to_thread_cancel`/`test_subtitle_ytdlp_opts` 中针对已删除旧链路的测试删除；仍有效的（上传安全、SSE 解析、恢复矩阵等）迁移到新文件。

## 7. 权衡

- **编排器落库终态 vs 阶段自落**：编排器统一落（阶段无 DB 依赖，可测性最大化；失败/取消语义一处定义）。
- **保留旧 stage 列**：历史任务列表展示需要；前端 C5 只消费新字段。
- **recover 放 orchestrator**：与调度同域，避免 routes.py 再持有业务逻辑。
