# 空状态时预选第一个 provider preset

## Goal

设置页中，当用户从未配置过 ASR / LLM（`SettingsResponse` 对应字段为 `null`）时，Provider 下拉不再显示空 placeholder，而是预选预设列表（`ProvidersResponse`）的第一个选项，并自动带出其 `api_base`，让用户"只填 API key 即可保存"。已保存过的配置回显逻辑保持不变。

## Background

- 现状：`SettingsPage.tsx` 的 `buildConfigForm` 在 `saved` 为 `null` 时返回 `emptyConfig`，Select 显示 placeholder「请选择服务商」，apiBase 为空。
- 业界参考（LobeChat / Cherry Studio 模式 A）：provider 多、预置信息丰富时，默认选中第一个 preset，用户只需填 key。
- 误选风险低：保存要求 API key 必填，预选 provider 不会导致误保存。

## Requirements

1. 前端 `buildConfigForm`：`saved` 为 `null` 且 `presets` 非空时，`provider` 取 `presets[0].provider`，`apiBase` 取 `presets[0].api_base`；`presets` 为空时维持现状（空表单）。
2. 已保存配置（含 custom provider fallback）的回显行为完全不变。
3. 用户主动切换 provider 时现有行为不变（清空 model、重置动态模型列表等）。
4. Model 字段仍为空（不预选模型），placeholder 提示不变。
5. i18n：不新增文案；若需要可复用现有 key。
6. 后端 `provider_routes.py` 预设顺序即"推荐默认"顺序，本任务不改后端，但在 PR 中说明该约定。

## Out of Scope

- 后端预设列表排序调整。
- Model 字段的默认预选。
- 保存后的 Warp 式"建议切换默认模型"引导。

## Acceptance Criteria

- [ ] 全新用户（无 ASR/LLM 配置）打开设置页：ASR 和 LLM 的 Provider 下拉均显示第一个预设的名称（非 placeholder），API Base 自动填充该预设的 `api_base`，API Key 为空。
- [ ] 已配置用户打开设置页：回显与改动前一致（含自定义 provider 场景）。
- [ ] `frontend` 相关测试通过（`npm test` / 现有测试命令）。
- [ ] 手动验证：预选状态下切换到其他 provider 再切回，表单状态正确。

## Notes

- Lightweight task：PRD-only。
- 涉及文件：`frontend/src/pages/SettingsPage.tsx`（`buildConfigForm`）。
