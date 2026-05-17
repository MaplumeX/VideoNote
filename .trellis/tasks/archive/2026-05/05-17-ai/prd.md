# AI 视频笔记总结软件 (VideoNote)

## Goal

开发一款 Web 应用，用户提交视频 URL 或上传本地文件，AI 自动提取内容并生成带时间戳的 Markdown 笔记，帮助快速获取视频核心信息。

## Requirements

* 支持三种视频来源：YouTube URL、Bilibili URL、本地文件上传
* 视频内容提取策略：智能降级——优先提取平台字幕，无字幕则走云端 ASR 转录
* 使用云端 LLM API 生成结构化笔记总结
* 使用云端 ASR API 处理无字幕视频
* 笔记输出为 Markdown 格式，包含时间戳对齐（如 `[00:01:30](#t=90)`）
* 无需用户登录，直接使用
* 核心流程：提交视频 → 处理 → 生成笔记 → 展示/下载
* 处理进度实时反馈（SSE）

## Acceptance Criteria

* [ ] 用户可提交 YouTube/Bilibili URL，系统自动提取字幕或转录音频
* [ ] 用户可上传本地视频文件，系统转录音频并生成笔记
* [ ] 生成的 Markdown 笔记包含标题层级、要点列表、时间戳引用
* [ ] 处理进度有 SSE 实时反馈
* [ ] 笔记可在线查看和下载

## Definition of Done

* 核心流程端到端可用（提交→处理→笔记）
* 代码通过 lint / typecheck
* 关键路径有测试覆盖

## Out of Scope (explicit)

* 用户登录/注册系统
* 笔记在线编辑
* 批量视频处理
* 笔记持久化存储/历史记录
* 多语言翻译
* 浏览器插件
* 本地模型/Whisper 本地部署
* 说话人分离（diarization）

## Research References

* [`research/video-processing-stack.md`](research/video-processing-stack.md) — 后端技术栈：ARQ 任务队列、yt-dlp 字幕提取、音频处理、ASR API 对比、SSE 进度推送
* [`research/frontend-and-structure.md`](research/frontend-and-structure.md) — 前端技术栈：Vite+React、Markdown 渲染、文件上传、SSE 客户端、monorepo 结构

## Technical Approach

### 架构

```
VideoNote/
├── backend/           # FastAPI (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/      # REST 端点
│   │   ├── services/  # 业务逻辑（字幕提取、ASR、LLM 总结）
│   │   └── schemas/  # Pydantic 模型
│   ├── worker.py      # ARQ 异步任务 worker
│   ├── pyproject.toml
│   └── tests/
├── frontend/          # React (Vite)
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── api/
│   │   ├── types/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
```

### 核心技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 前端框架 | Vite + React 19 | SPA 场景，Vite 极速 HMR，CRA 已废弃 |
| UI 组件 | 无头 UI (Radix/shadcn) + Tailwind CSS | 极轻量，完全自定义样式 |
| Markdown 渲染 | react-markdown + remark-gfm | `components` prop 支持自定义时间戳组件 |
| 文件上传 | react-dropzone | 6KB，拖拽+选择，XHR 进度条 |
| 后端框架 | FastAPI | Python 生态与 yt-dlp/Whisper 集成最佳 |
| 异步任务队列 | ARQ | asyncio 原生、仅依赖 Redis、MVP 最简 |
| 实时进度 | SSE (sse-starlette) | 单向推送足够，自动重连，比 WS 简单 |
| 视频下载/字幕 | yt-dlp | YouTube/Bilibili 标准工具 |
| 音频提取 | ffmpeg (subprocess) | WAV PCM 16kHz mono，ASR 通用兼容格式 |
| 语音转录 | OpenAI Whisper API | 最简集成，中英文均好，$0.006/min |
| AI 总结 | 云端 LLM API | OpenAI / Anthropic / DeepSeek 等 |

### 核心流程

1. 用户提交视频 URL 或上传文件
2. 后端创建 ARQ 任务，返回 job_id
3. ARQ worker 执行：
   - 在线视频：yt-dlp 提取字幕 → 无字幕则下载音频 → Whisper API 转录
   - 本地文件：ffmpeg 提取音频 → Whisper API 转录
4. 将转录文本发送给 LLM API 生成 Markdown 笔记（含时间戳）
5. 前端通过 SSE 实时接收进度，完成后展示/下载笔记

### 关键风险

* Bilibili CC 字幕覆盖率低，多数视频需降级到 ASR 转录
* Bilibili API 不稳定，yt-dlp 需定期更新
* OpenAI Whisper API 25MB 文件限制，长音频需分片
* 本地环境访问 YouTube 可能有网络/代理问题

## Decision (ADR-lite)

**Context**: 需要在多种异步任务队列、ASR 服务、前端框架间选择
**Decision**: ARQ + OpenAI Whisper API + Vite React + SSE，MVP 最简组合
**Consequences**: 后期如需扩展到 Celery（大规模分布式）或 Alibaba ASR（中文优化）可平滑迁移，核心任务逻辑不变
