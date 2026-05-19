# Move Language Switch to Settings Page

## Goal

将语言切换从侧边栏的"点击即切换"按钮移至设置页面，改为下拉选择器 UI，让语言切换属于设置行为而非快捷操作。

## What I already know

* 当前语言切换按钮在 `Sidebar.tsx` 底部（Globe 图标 + 对方语言名），点击立即切换，无确认
* 设置页面 `SettingsPage.tsx` 已有 ASR/LLM 两个 ProviderConfigSection，页面路由 `/app/settings`
* i18n 架构：i18next + react-i18next + browser-languagedetector，支持 `en` / `zh-CN`
* 当前语言通过 `i18n.resolvedLanguage` 读取，通过 `i18n.changeLanguage()` 切换
* 语言持久化在 localStorage（key: `i18n-lang`），由 i18next-browser-languagedetector 管理
* 已有 `SUPPORTED_LANGS` 导出：`["en", "zh-CN"]`
* 翻译文件中已有 `lang.label`（"语言"/"Language"）和 `lang.switch` 键

## Assumptions (temporary)

* 语言切换后不需要页面刷新或重新加载，i18next 会自动热更新所有翻译
* 设置页中的语言选择器应该即时生效（选完就切），但不同于"点击即切换"的按钮，选择器是明确的设定行为
* 不需要额外的确认弹窗

## Open Questions

(none remaining)

## Decision (ADR-lite)

**Context**: 语言选择器 UI 形式选择
**Decision**: 下拉 select，与现有 Provider select 风格一致
**Consequences**: 视觉统一，未来增加语言无需改 UI 结构

## Requirements

* 从 Sidebar 中移除语言切换按钮（Globe 图标 + toggleLang）
* 在 SettingsPage 中新增"语言"设置区块，放在 ASR/LLM 配置之前
* 语言选择器使用 select 下拉框，复用 ProviderConfigSection 中的 selectClass 样式
* 选择语言后即时生效（i18n.changeLanguage），无需额外保存按钮
* 下拉框显示当前语言为选中状态
* 侧边栏移除语言按钮后不保留任何语言入口

## Acceptance Criteria (evolving)

- [ ] Sidebar 中不再有语言切换按钮
- [ ] SettingsPage 有"语言"设置区块，包含下拉选择器
- [ ] 选择语言后即时切换，所有 UI 文字更新
- [ ] 刷新页面后语言设置持久化（localStorage）
- [ ] 下拉框显示当前语言为选中状态

## Definition of Done

* Lint / typecheck 通过
* 手动验证切换功能正常

## Out of Scope

* 新增语言支持
* 语言切换确认弹窗
* 服务端语言偏好同步

## Technical Notes

* 关键文件：`Sidebar.tsx`、`SettingsPage.tsx`、`i18n/index.ts`、`i18n/locales/*.json`
* Sidebar 中 `toggleLang` 函数和 `Globe` 图标 import 可移除
* SettingsPage 中需要 `useTranslation` 获取 `i18n` 实例
* 可复用 `SUPPORTED_LANGS` 导出构建选项列表
* 语言选项显示名需要映射：`en` → "English", `zh-CN` → "中文"
