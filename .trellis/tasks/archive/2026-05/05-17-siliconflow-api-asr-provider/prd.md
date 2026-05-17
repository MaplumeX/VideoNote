# 支持 SiliconFlow 转录 API 作为 ASR Provider

## Goal

让用户可以通过配置 `ASR_PROVIDER=siliconflow` 使用 SiliconFlow 的语音转录 API（SenseVoiceSmall / TeleSpeechASR），而非仅限 OpenAI Whisper。

## Requirements

* 新增 `ASR_PROVIDER` 环境变量，支持 `openai`（默认）和 `siliconflow`
* `siliconflow` 模式下：不传 `language`/`response_format`/`timestamp_granularities`，仅传 `file` + `model`
* `siliconflow` 模式下：文件大小限制调整为 50MB（Whisper 保持 25MB）
* `siliconflow` 模式下：响应无 segments，直接返回纯文本
* `openai` 模式行为与当前完全一致，零改动

## Acceptance Criteria

* [ ] 设置 `ASR_PROVIDER=siliconflow` + `ASR_API_KEY` + `ASR_MODEL=FunAudioLLM/SenseVoiceSmall` 后，转录正常返回文本
* [ ] 默认 `ASR_PROVIDER=openai` 时行为与当前完全一致
* [ ] `.env.example` 更新，文档说明新配置项
* [ ] 大文件（>25MB ≤50MB）在 siliconflow 模式下不切分，直接发送

## Definition of Done

* 代码变更通过 lint/typecheck
* 手动验证两种 provider 模式均可正常转录

## Technical Approach

在 `config.py` 新增 `ASR_PROVIDER`，`transcribe.py` 根据 provider 值分支处理：

* `openai`：保持现有逻辑（verbose_json + segments + 时间戳 + 25MB 切分）
* `siliconflow`：精简参数（仅 file + model），50MB 限制，返回纯文本

不引入抽象类/策略模式——两个 provider 的差异仅在 `_transcribe_file` 的调用参数和大小限制，用条件分支即可，过度抽象反而增加理解成本。

## Decision (ADR-lite)

**Context**: SiliconFlow 转录 API 无时间戳返回，需决定输出格式
**Decision**: SiliconFlow 模式下接受纯文本，不做时间戳补偿
**Consequences**: 笔记无时间定位链接，功能相对 Whisper 有退化；未来可考虑按固定时长估算伪时间戳或双路对齐作为增强

## Out of Scope

* 时间戳补偿/伪时间戳估算
* 非 OpenAI 兼容的 provider（阿里云、讯飞等需要独立 SDK 的）
* provider 抽象层/策略模式重构

## Technical Notes

* 关键文件：`backend/app/services/transcribe.py`, `backend/app/config.py`, `.env.example`
* SiliconFlow API 文档：https://docs.siliconflow.cn/cn/api-reference/audio/create-audio-transcriptions
* SiliconFlow 可用模型：`FunAudioLLM/SenseVoiceSmall`、`TeleAI/TeleSpeechASR`
