# 支持自定义 LLM 提供商（转录 + 笔记生成）

## Goal

让转录（ASR）和笔记生成（LLM）各自独立配置 OpenAI 兼容 API 提供商，用户通过环境变量即可切换，不再硬绑定 OpenAI。

## Requirements

* ASR 环节支持独立的 `ASR_API_KEY` / `ASR_API_BASE` / `ASR_MODEL` 环境变量，可指向任意 OpenAI 兼容 Whisper 端点
* LLM 笔记生成环节保持现有 `LLM_API_BASE` / `LLM_MODEL`，新增独立的 `LLM_API_KEY`（不再复用 `OPENAI_API_KEY`）
* ASR 和 LLM 可使用不同的提供商、不同的 API key
* 向后兼容：未设置新变量时，fallback 到 `OPENAI_API_KEY` + OpenAI 默认值
* `.env.example` 更新反映所有新配置项

## Acceptance Criteria

* [ ] 设置 `ASR_API_BASE` 指向非 OpenAI 端点后，转录正常工作
* [ ] 设置 `LLM_API_BASE` 指向非 OpenAI 端点 + `LLM_API_KEY` 后，笔记生成正常工作
* [ ] ASR 和 LLM 使用不同 API key 时各自独立工作
* [ ] 不设置新变量时行为与当前一致（向后兼容）
* [ ] `.env.example` 包含所有新配置项及说明

## Definition of Done

* Tests added/updated
* Lint / typecheck green
* `.env.example` 更新

## Technical Approach

**环境变量设计**（向后兼容）：

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | 通用 fallback key | `""` |
| `ASR_API_KEY` | ASR 专用 key | `OPENAI_API_KEY` |
| `ASR_API_BASE` | ASR 专用 base URL | `https://api.openai.com/v1` |
| `ASR_MODEL` | ASR 模型名 | `whisper-1` |
| `LLM_API_KEY` | LLM 专用 key | `OPENAI_API_KEY` |
| `LLM_API_BASE` | LLM 专用 base URL | `https://api.openai.com/v1` |
| `LLM_MODEL` | LLM 模型名 | `gpt-4o` |

**代码改动**：

1. `config.py` — 新增 `ASR_API_KEY`、`ASR_API_BASE`、`ASR_MODEL`、`LLM_API_KEY`，均 fallback 到 `OPENAI_API_KEY` / OpenAI 默认
2. `transcribe.py` — 使用 `ASR_API_KEY` + `ASR_API_BASE` + `ASR_MODEL` 替代硬编码
3. `note_gen.py` — 使用 `LLM_API_KEY` 替代 `OPENAI_API_KEY`
4. `.env.example` — 更新注释和示例

## Decision (ADR-lite)

**Context**: 转录硬编码 OpenAI Whisper API，笔记生成虽支持 `LLM_API_BASE` 但 key 复用 `OPENAI_API_KEY`，两者无法独立配置不同提供商。

**Decision**: ASR 和 LLM 各自独立的 `API_KEY` / `API_BASE` / `MODEL` 三件套，均走 OpenAI 兼容 API，不引入额外 SDK。新变量未设置时 fallback 到 `OPENAI_API_KEY` + OpenAI 默认值以保持向后兼容。

**Consequences**: 支持任意 OpenAI 兼容端点（vLLM、Ollama、Azure 等）；不支持原生 Anthropic/Gemini SDK（需通过兼容代理层）；本地 faster-whisper 离线模式需未来单独任务。

## Out of Scope

* 前端 UI 选择提供商
* 自动 fallback（主提供商失败自动切备用）
* 本地 faster-whisper 离线转录
* 原生 Anthropic/Gemini SDK 支持

## Technical Notes

* `backend/app/config.py` — 新增环境变量
* `backend/app/services/transcribe.py` — ASR 客户端改造
* `backend/app/services/note_gen.py` — LLM key 改造
* `backend/.env` + `.env.example` — 配置更新
