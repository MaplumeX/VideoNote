# 技术设计：核心流水线重写（父任务层）

> 本文档是跨子任务的总体架构设计。各子任务在自己的 design.md 中细化局部设计，但不得违背此处定义的边界与契约。

## 1. 目标架构

```
routes.py (瘦 API 层，只做参数校验/鉴权/HTTP 映射)
    │
    ▼
pipeline/ (新包，编排核心)
    ├── orchestrator.py      # 状态机驱动的阶段执行器：从检查点恢复、调度、终态落库
    ├── stages/              # 每个阶段一个模块，输入/输出为纯数据
    │   ├── fetch.py         #   视频元信息 + 缩略图（yt-dlp 子进程）
    │   ├── subtitle.py      #   字幕提取 + SRT/VTT 解析
    │   ├── audio.py         #   音频下载/提取（yt-dlp/ffmpeg 子进程）
    │   ├── transcribe.py    #   异步 ASR 客户端 + 大文件切块
    │   └── notegen.py       #   异步 LLM 笔记生成 + 分块/合并/续写
    ├── state.py             #   TaskStage/Phase/检查点数据模型（C1 产出）
    ├── errors.py            #   统一错误码枚举 + PipelineError + 脱敏（C1 产出）
    ├── progress.py          #   两级进度模型与事件发布（C1 产出）
    └── subprocess_util.py   #   子进程托管：spawn/wait/kill，与 asyncio 取消联动（C2 产出）
```

- 旧 `services/` 中被重写的模块在 C4 完成后删除；未被重写的（如 `markdown.py` 归一化）迁移或保留。
- `task_runner.py` 的「防重复调度」职责保留，取消职责移交编排器（asyncio 原生取消，不再用 threading.Event）。

## 2. 数据流与契约

### 2.1 阶段状态机（C1 定义，契约文档固化）

URL 路径：`pending → fetching → subtitle → (transcribe ← audio 前置) → notegen → complete`
文件路径：`pending → audio → transcribe → notegen → complete`
每阶段成功即写检查点（阶段名 + 中间产物），失败进入 `failed(code)`，取消进入 `cancelled`。

### 2.2 中间产物持久化

- tasks 表新增：`checkpoint_stage`、`attempt_count`（已有 attempt 语义整合）、`last_error_code`。
- 新表 `task_artifacts`：`job_id, kind(subtitle|transcript|video_meta), content_json, created_at`。
- 恢复规则：重试/重启时读取最后检查点，跳过已有产物阶段；无产物则从头执行该阶段。

### 2.3 SSE / API 契约（破坏性变更，C1 固化 schema）

- `progress` 事件载荷升级为：`{stage, phase_progress, message, attempt, timestamp}`；`stage` 为新阶段枚举，`phase_progress ∈ [0,1]` 为阶段内进度。
- REST：`POST /tasks/{id}/retry` 语义增强（从检查点恢复）；其余端点路径不变，响应模型按新枚举更新。
- 兼容策略：**不设兼容层**，前后端同任务树内同步切换（D2）。

### 2.4 取消语义

- 编排器持有每个运行阶段的「取消句柄」：子进程为 `Process.kill()`，异步 SDK 为 `asyncio.Task.cancel()`（AsyncOpenAI 请求随之中止）。
- 取消流程：API 收到 cancel → 落库 cancelled 意图 → 编排器感知 → 终止当前阶段句柄 → 阶段清理 → 终态落库。目标 ≤3s。
- 不再向线程轮询 `threading.Event`；同步库（yt-dlp Python API）改为子进程 CLI 调用以便可 kill。

## 3. 关键权衡

| 决策 | 选择 | 理由 | 放弃项 |
|------|------|------|--------|
| yt-dlp 集成方式 | 子进程 CLI（`yt-dlp` 命令 + `--print-json`） | 可 kill、崩溃隔离、asyncio 原生集成 | Python API（取消不深入，历史 bug 源头） |
| ASR/LLM 客户端 | AsyncOpenAI | 取消即时、事件循环内无线程泄漏 | to_thread 包同步客户端 |
| 检查点粒度 | 阶段级（字幕/转录文本整体） | 粒度够用、实现简单；ASR chunk 级恢复成本高收益低 | chunk 级恢复 |
| 进度模型 | 阶段 + 阶段内 fraction | 前端可准确渲染步骤状态，后端无需维护全局魔法区间 | 全局百分比 |
| 部署形态 | 保持单进程 + SQLite | 项目明确决策过（历史任务档案） | Redis/ARQ 等队列 |

## 4. 子任务边界与接口

- **C1 产出契约**（state.py/errors.py/progress.py + 契约文档 `.trellis/tasks/*/contract.md` 或 docs）：C2/C3/C4/C5 全部依赖；C1 先行，完成即冻结契约，变更需回父任务评审。
- **C2/C3 对 C4 的接口**：stages 模块签名统一为 `async def run(ctx: StageContext) -> StageResult`，ctx 携带产物读写器、进度发布器、取消句柄注册器、Provider 配置。
- **C4 消费** C2/C3 的 stage 实现 + C1 的状态机/持久层，重写编排与 API 层，删除旧链路。
- **C5 消费** C4 落地后的实际 SSE 端点 + C1 契约文档。

## 5. 兼容与迁移

- DB：新增列/表均为增量迁移（沿用 `schema_version` 机制），旧 tasks 行 checkpoint 为空 → 视为需从头执行（首次重试时自然迁移）。
- 发布：破坏性变更集中在一个 release；`docker-compose` 单镜像不变。
- 回滚：每个子任务独立 PR/commit，可单独 revert；C4 是新旧链路切换点（切换前旧链路完整保留）。

## 6. 风险

- yt-dlp CLI 与 Python API 行为差异（cookie/格式选择）→ C2 需 fixture 实测对比。
- SQLite 写检查点的频率（每阶段一次，量小无压力）。
- 前端切换窗口：C4 合入后 C5 完成前 UI 不可用 → 安排 C4/C5 紧邻实施，或同分支连续合入。
