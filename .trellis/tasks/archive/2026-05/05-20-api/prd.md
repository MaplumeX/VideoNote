# 增强 API 模型选择方案

## Goal

增强 VideoNote 中 AI 模型的选择和配置机制，让用户能更灵活、更直观地选择和切换 ASR/LLM 模型。

## What I already know

* 后端通过环境变量 (`ASR_MODEL`, `LLM_MODEL` 等) 设全局默认
* 前端 Settings 页面有 provider+model 下拉选择，基于 `PROVIDER_PRESETS` 硬编码列表
* 预设列表当前仅 2 个 ASR provider (openai, siliconflow) + 2 个 LLM provider (openai, deepseek)
* 每个预设 provider 下只列 1-2 个模型
* 支持自定义 provider（手动填写 provider 名称、model 名称、api_base）
* 用户配置存储在 SQLite `user_providers` 表，API key 用 Fernet 加密
* 所有 API 调用统一走 OpenAI SDK，兼容任何 OpenAI-compatible endpoint
* LLM 调用固定参数：`temperature=0.3`, `max_tokens=4096`

## Assumptions (temporary)

* 用户希望扩展预设 provider/模型列表（如增加 Google Gemini、Qwen 等）
* 用户可能希望模型列表能动态获取而非硬编码
* 用户可能希望 LLM 调用参数可配置（如 temperature、max_tokens）

## Open Questions

* (无 — 所有关键问题已解决)

## Requirements (evolving)

* 动态模型发现：选择 provider 后，后端代理调用 `/v1/models`，自动拉取该 provider 下可用模型列表
* 手动填写模型：使用 Combobox（可搜索下拉框），同时支持从列表选择和自由输入任意模型名
* 保留现有 provider 预设 + 自定义 provider 功能
* 后端新增 `POST /api/models` 端点，代理模型列表请求（避免前端暴露 API key）
* 前端 Settings 页面模型输入从固定下拉框改为 Combobox
* 选择 provider + 填完 API key 后自动触发模型列表拉取

## Acceptance Criteria (evolving)

* [ ] 选择预设 provider + 填入 API key 后，Combobox 自动加载该 provider 的可用模型列表
* [ ] 选择自定义 provider（填写 api_base + api_key）后，也能动态拉取模型列表
* [ ] 用户可在 Combobox 中输入任意模型名，不限于下拉列表中的选项
* [ ] 模型列表获取失败时降级为空列表，Combobox 仍可手动输入
* [ ] 后端代理 `/v1/models` 请求，API key 不经前端直接发送到第三方

## Decision (ADR-lite)

**Context**: 模型选择 UX 需要兼顾动态列表和自由输入
**Decision**: 采用 Combobox（可搜索下拉框），既展示动态获取的模型列表，又允许用户直接输入任意模型名
**Consequences**: 需要引入或实现 Combobox 组件；体验更流畅但实现稍复杂于纯下拉框

## Out of Scope (explicit)

* 前端模型类型过滤（ASR/LLM/TTS 混杂列表的智能分类）
* 后端模型列表缓存（后续可加）
* LLM 调用参数可调（temperature, max_tokens）
* 扩展预设 provider 列表

## Definition of Done

* Tests added/updated
* Lint / typecheck / CI green
* 前后端类型同步
* 数据库迁移（如有 schema 变更）

## Out of Scope (explicit)

* (待定)

## Technical Notes

* 后端配置: `backend/app/config.py` (PROVIDER_PRESETS, env vars)
* API 路由: `backend/app/routes.py` (provider resolution, /api/providers)
* 前端 Settings: `frontend/src/pages/SettingsPage.tsx` (ProviderConfigSection)
* 前端 API: `frontend/src/api/client.ts` (fetchProviders, fetchSettings, saveSettings)
* 前端类型: `frontend/src/types/index.ts`
* ASR 服务: `backend/app/services/transcribe.py`
* LLM 服务: `backend/app/services/note_gen.py`
* 数据库: `backend/app/db.py` (user_providers table)
* 加密: `backend/app/crypto.py`
