# 前端 Provider/模型选择功能

## Goal

让用户在前端界面选择 ASR（语音转写）和 LLM（笔记生成）的 Provider 与模型，替代当前纯后端环境变量配置的方式，使配置可视化、可切换。

## What I already know

* 后端当前通过环境变量配置 ASR/LLM：`ASR_PROVIDER`, `ASR_MODEL`, `ASR_API_KEY`, `ASR_API_BASE`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`
* 前端完全没有任何设置/配置 UI
* `/api/process` 和 `/api/upload` 端点仅接受 `url` + `language`，不支持指定 provider/model
* `transcribe_audio()` 和 `generate_notes()` 从模块级 import 读取配置，不支持运行时参数传入
* 已有的 .env 配置：ASR 用 SiliconFlow（SenseVoiceSmall），LLM 用 DeepSeek（deepseek-v4-flash）
* 两者的 API 均使用 OpenAI SDK（兼容 OpenAI API 格式），切换 provider 只需改 base_url + api_key + model

## Decision (ADR-lite)

**Context**: API Key 管理方式决定了安全边界和架构复杂度
**Decision**: 方案 B — 前端传入 API Key，后端不持久化
**Consequences**: Key 经网络传输（依赖 HTTPS），前端需安全存储方案，用户可用自己的 Key

**Context**: Provider/模型列表的来源决定了前端约束度与灵活性
**Decision**: A+C 混合 — 后端返回预设 Provider+Model 列表供下拉选择，同时提供"自定义"入口允许手动填写任意 OpenAI 兼容端点
**Consequences**: 常见 provider 一键选择，高级用户不受限；后端需新增 `/api/providers` 端点

**Context**: Provider/模型选择 UI 的位置影响操作流程
**Decision**: 方案 B — 独立设置页 `/app/settings`，配置全局保存
**Consequences**: 配置与操作分离，主界面保持简洁；需新增路由和导航入口

**Context**: API Key 存储位置影响安全架构和跨设备体验
**Decision**: 存后端 DB，加密存储
**Consequences**: 需新增 DB 表存用户 provider 配置、服务端需加密/解密 Key、跨设备同步可用、前端零 Key 持久化

## Open Questions

* (无 — 所有核心决策已确认)

## Requirements (evolving)

* 前端提供 Provider/Model 选择 UI
* 后端支持接收并使用用户选择的 provider/model + API Key
* 支持 ASR 和 LLM 两个维度的独立选择
* API Key 由前端传入后端，不经后端持久化
* 后端提供 `/api/providers` 返回预设 Provider+Model 列表
* 前端支持"自定义"入口，允许手动填写 API Base / Model / Key
* 独立设置页 `/app/settings`，从导航栏进入
* API Key 存后端 DB，加密存储，前端不持久化 Key
* 设置页回显 Key 时脱敏（仅显示后 4 位）
* 未配置 Provider 时 fallback 到后端环境变量默认值

## Acceptance Criteria (evolving)

* [ ] 用户可以在前端选择 ASR Provider + Model
* [ ] 用户可以在前端选择 LLM Model
* [ ] 提交任务时选择生效，后端使用用户选择的配置执行
* [ ] 设置页回显 API Key 时脱敏（仅显示后 4 位）

## Definition of Done

* Lint / typecheck green
* 功能可端到端验证

## Out of Scope (explicit)

* (待确认)

## Technical Notes

* 后端 config: `backend/app/config.py`
* ASR 服务: `backend/app/services/transcribe.py` — `OpenAI(api_key=ASR_API_KEY, base_url=ASR_API_BASE)`
* LLM 服务: `backend/app/services/note_gen.py` — `OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)`
* 路由: `backend/app/api/routes.py` — `_process_video_url()` 和 `_process_video_file()` 调用上述服务
* 前端提交: `frontend/src/api/client.ts`, `frontend/src/components/VideoInput.tsx`
* Schema: `backend/app/schemas.py` — `VideoRequest` 只有 url + language
