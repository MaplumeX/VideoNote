# 技术设计：C1 任务状态机与持久层（契约基线）

> 父任务 design.md §1/§2 的契约部分在此细化。本任务产出的契约在 G1 门禁通过后冻结。

## 1. 模块布局（本任务产出）

```
backend/app/pipeline/
├── __init__.py
├── state.py        # 任务状态 + 流水线阶段 + 路径定义 + 状态转移表 + 检查点模型
├── errors.py       # 错误码枚举 + PipelineError + 集中脱敏
├── progress.py     # 两级进度模型 + ProgressPublisher 协议 + 单调性守卫
└── stages/
    └── base.py     # StageContext / StageResult / Stage 协议（C2/C3 的实现目标）
```

不改动 `app/services/`、`app/api/routes.py`、`app/task_runner.py` 的现有行为——旧链路在 C4 前保持完整可用。DB 仅做增量迁移（新列/新表），旧列不动。

## 2. state.py 设计

### 2.1 任务状态与阶段分离（核心语义变更）

旧 `TaskStage` 把「任务生命周期状态」和「处理阶段」混在一个枚举里（pending/downloading/extracting_subtitles/transcribing/generating_notes/complete/failed/cancelled）。新模型拆分：

```python
class TaskStatus(StrEnum):
    pending = "pending"        # 已创建未调度
    running = "running"        # 执行中（phase 指明当前阶段）
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"

class PipelinePhase(StrEnum):
    fetching = "fetching"        # URL: 视频元信息 + 缩略图
    subtitle = "subtitle"        # URL: 字幕提取（命中则跳过 audio+transcribe）
    audio = "audio"              # 音频下载/提取
    transcribe = "transcribe"    # ASR 转录
    notegen = "notegen"          # LLM 笔记生成
```

### 2.2 路径定义与转移表

```python
URL_PATH:  [fetching, subtitle, audio, transcribe, notegen]
FILE_PATH: [audio, transcribe, notegen]
```

- URL 路径中 `subtitle` 命中后**跳过** `audio`+`transcribe` 直达 `notegen`（条件跳转，转移表显式表达）。
- 转移表 `ALLOWED_TRANSITIONS: dict[PipelinePhase | None, set[PipelinePhase]]`：
  - `None(start) → fetching | audio`；`fetching → subtitle | failed`
  - `subtitle → audio | notegen`（未命中字幕 → audio；命中 → notegen）
  - `audio → transcribe`；`transcribe → notegen`；`notegen → None(完成)`
- `validate_transition(src, dst)` 抛 `InvalidTransitionError`；提供 `next_phases(path, current)` 查询。

### 2.3 检查点模型

```python
@dataclass(frozen=True)
class Checkpoint:
    completed_phase: PipelinePhase   # 最后成功完成的阶段
    artifacts: frozenset[ArtifactKind]
```

恢复规则（`resume_point(path, checkpoint) -> PipelinePhase`）：从 checkpoint.completed_phase 的下一个允许阶段开始；无 checkpoint → 路径首阶段。字幕命中导致的后跳由转移表 + 产物查询共同决定（有 subtitle 产物即直达 notegen）。

## 3. errors.py 设计

```python
class ErrorCode(StrEnum):
    # 视频获取（yt-dlp 分类，语义迁移自 classify_ytdlp_error）
    VIDEO_PRIVATE; VIDEO_GEO_RESTRICTED; VIDEO_NOT_FOUND
    VIDEO_COOKIE_INVALID; VIDEO_FETCH_FAILED
    # 阶段失败
    SUBTITLE_EXTRACTION_FAILED; AUDIO_EXTRACTION_FAILED
    TRANSCRIPTION_FAILED; NOTE_GENERATION_FAILED
    # 任务/系统
    PROCESSING_FAILED; PROVIDER_NOT_CONFIGURED
    TASK_RECOVERY_MAX_ATTEMPTS; TASK_RECOVERY_INPUT_INVALID
    TASK_RECOVERY_UNSUPPORTED_URL; TASK_CANCELLED
    # 保留：MODELS_FETCH_FAILED 等非流水线码继续留在 app/errors.py，不迁移

class PipelineError(Exception):
    code: ErrorCode
    detail: str          # 已脱敏、≤200 字符
    def __init__(self, code, *, detail="", cause=None): ...

def sanitize_detail(text: str) -> str: ...   # 迁移 routes.py 的 _sanitize_error_detail（API key/Bearer/cookie 正则）
```

规则：`PipelineError` 的 `detail` 在构造时即脱敏（构造函数内调用 `sanitize_detail`），后续任何层拿到的 detail 都是安全的——把「忘记脱敏」做成结构性不可能。

## 4. progress.py 设计

```python
@dataclass(frozen=True)
class ProgressEvent:
    status: TaskStatus
    phase: PipelinePhase | None
    phase_progress: float      # ∈ [0,1]，阶段内进度
    message: str               # 展示文案或错误码
    attempt: int
    timestamp: str             # ISO 8601

class ProgressPublisher(Protocol):
    async def publish(self, phase: PipelinePhase, fraction: float, message: str) -> None: ...

class PhaseProgressTracker:
    """阶段内单调守卫：同 phase 下 fraction 只升不降；换 phase 重置。"""
    def update(self, phase, fraction) -> float   # clamp [0,1]，非单调时取 max 并告警日志
```

全局百分比废除；前端如需总进度可按「阶段序号 + fraction」自行合成（契约文档注明）。

## 5. stages/base.py 设计（C2/C3 的实现契约）

```python
@dataclass
class StageContext:
    job_id: str
    language: str
    provider: ProviderConfig          # dataclass：asr/llm 的 key/base/model/provider
    artifacts: ArtifactStore          # 读写中间产物（见 §6）
    progress: ProgressPublisher
    register_cancel: CancelHandleRegistrar   # 注册子进程/任务取消句柄，C4 编排器提供实现

@dataclass
class StageResult:
    outputs: dict[ArtifactKind, object]   # 本阶段产出（由编排器落库）

class Stage(Protocol):
    phase: ClassVar[PipelinePhase]
    async def run(self, ctx: StageContext, *, resume: bool) -> StageResult: ...
```

`ArtifactStore` 协议：`async get(kind) -> object | None`、`async put(kind, content)`。C1 提供 DB 实现的接口定义与协议（实现即 db.py 的 artifacts 函数，见 §6）。

## 6. DB 迁移（app/db.py 增量）

沿用 schema_version / try-except OperationalError 迁移模式：

- `tasks` 新增列：`status TEXT`、`phase TEXT`、`phase_progress REAL`、`checkpoint_phase TEXT`、`last_error_code TEXT`。旧列 `stage`/`progress` 原样保留（旧链路继续用；C4 切换后不再写入，物理删除不做）。
- 存量数据回填（一次性 UPDATE）：旧 `stage` 值映射到新 `status`（`pending→pending`；`downloading/extracting_subtitles/transcribing/generating_notes→running`；`complete/failed/cancelled→同名`），`checkpoint_phase=NULL`（旧任务无检查点，语义=从头执行）。
- 新表：
  ```sql
  CREATE TABLE IF NOT EXISTS task_artifacts (
      job_id TEXT NOT NULL,
      kind TEXT NOT NULL,             -- video_meta | subtitle | transcript | notes_draft
      content_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (job_id, kind)
  );
  ```
- 新增 DB 函数：`save_artifact(job_id, kind, content)`、`get_artifact(job_id, kind)`、`save_checkpoint(job_id, phase, status/phase_progress 条件写)`、`read_checkpoint(job_id)`。检查点/进度写入复用既有条件写模式（`WHERE status NOT IN (terminal)` + `cancel_requested = 0`，见 database-guidelines「Durable Single-Process Video Tasks」契约）。

## 7. 契约文档（docs/pipeline-contract.md）

内容：任务状态/阶段枚举与转移图、路径定义（URL/FILE + 字幕条件跳转）、`ProgressEvent` SSE 载荷 JSON schema、`task_artifacts` kinds 表、错误码全表（含脱敏规则说明）、Stage/StageContext 接口。这是 C2~C5 的唯一契约事实源。

## 8. 测试设计

- `tests/pipeline/test_state.py`：全转移合法性矩阵、非法转移拒绝、两条路径 next_phases、resume_point（含字幕命中跳过）。
- `tests/pipeline/test_errors.py`：脱敏用例（sk-key/Bearer/cookie/超长截断）、PipelineError 自动脱敏。
- `tests/pipeline/test_progress.py`：clamp、单调守卫（同 phase 回退被拒、换 phase 重置）。
- `tests/pipeline/test_db_migration.py`：内存 SQLite 上旧 schema → 迁移 → 回填断言；artifact 读写；条件写（cancelled 赢过进度写入）。

## 9. 权衡与边界

- **status/phase 拆分 vs 沿用单枚举**：拆分。旧枚举是进度回退 bug 的直接原因之一（阶段与终态混用导致转移校验无从做起）。
- **checkpoint 粒度阶段级**（父任务已决策）；`notes_draft` kind 预留给 C3 多块中间态（契约预留，C1 不实现写入方）。
- **不动旧链路**：C1 只加不改，保证 C2/C3 期间主分支随时可发布。
