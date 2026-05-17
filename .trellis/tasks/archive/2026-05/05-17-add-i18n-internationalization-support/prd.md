# Add i18n Internationalization Support

## Goal

为 VideoNote 应用添加国际化(i18n)支持，使前端 UI 文本可切换语言，为多语言用户群提供本地化体验。

## What I already know

* 前端：React 19 + Vite + TypeScript + Tailwind CSS
* 前端无现有 i18n 框架或国际化代码
* 后端：Python FastAPI，进度消息等硬编码英文
* 前端硬编码字符串分布：
  * `App.tsx`: "VideoNote", "AI-powered video notes with timestamps", "Uploading video...", "Download Markdown", "New Video", "Failed to submit URL", "Upload failed"
  * `VideoInput.tsx`: "Video URL", "Upload File", "Paste YouTube or Bilibili URL...", "Process", "Drag & drop a video file, or click to browse", "Drop video here...", "MP4, WebM, MKV, etc."
  * `ProgressBar.tsx`: STAGE_LABELS 全部英文 ("Queued", "Downloading video", "Extracting subtitles", "Transcribing audio", "Generating notes", "Complete", "Failed")
* 后端消息也为英文硬编码（"Extracting subtitles...", "No subtitles, downloading audio..." 等），但这些是 SSE 推送的进度消息，i18n 责任可由前端承担

## Assumptions (temporary)

* MVP 支持中文(zh-CN)和英文(en)
* i18n 范围覆盖前端 UI 文本 + 后端 prompt
* 后端 prompt 根据前端传递的 language 参数选择对应语言模板
* 不做服务端进度消息 i18n（前端用 stage key 做本地化映射）

## Decision (ADR-lite)

**Context**: 选择 i18n 库，需平衡包体积与生态扩展性
**Decision**: 使用 react-i18next + i18next
**Consequences**: 增加 ~30-40KB gzipped 依赖，但获得成熟生态（语言检测、懒加载、命名空间），未来扩展零成本

## Open Questions

*(全部已解决)*

## Requirements (evolving)

* 所有前端 UI 硬编码文本提取为翻译 key
* 默认跟随浏览器语言(navigator.language)，手动切换后偏好存 localStorage
* Header 右上角提供语言切换按钮
* 翻译文件按语言组织
* 前端提交任务时附带当前语言参数(language)，后端据此选择 prompt 模板
* 后端 prompt 按语言组织模板，控制生成笔记的语言

## Acceptance Criteria (evolving)

* [ ] 前端所有可见文本均通过 i18n 系统渲染
* [ ] 支持至少 2 种语言切换
* [ ] 切换语言后 UI 文本即时更新，无需刷新
* [ ] 浏览器语言检测自动选择对应语言
* [ ] 手动切换后偏好持久化到 localStorage
* [ ] 前端提交任务时附带 language 参数
* [ ] 后端根据 language 参数选择对应语言的 prompt 模板
* [ ] build 通过，无 lint/typecheck 错误

## Definition of Done

* Lint / typecheck / build 通过
* 翻译文件结构清晰可扩展

## Out of Scope

* 后端进度消息 i18n
* RTL 布局支持
* 日期/数字格式本地化

## Technical Notes

* React 19 + Vite 环境
* 前端约 4 个组件有硬编码文本
* STAGE_LABELS 在 ProgressBar 中是前端对 stage key 的映射，可直接 i18n 化
* 后端 SSE 的 message 字段为英文 → 前端可忽略 message，用 stage + i18n 映射展示
* 后端 note_gen.py 的 SYSTEM_PROMPT 和 user_content 为英文硬编码，需按语言组织 prompt 模板
* API 需新增 language 参数：VideoRequest schema + upload endpoint
* 后端 prompt 模板按语言组织（如 backend/app/services/prompts/{en,zh_CN}.py 或 dict 映射）

## Research References

* [`research/react-i18n-libraries.md`](research/react-i18n-libraries.md) — react-i18next 推荐，React 19 兼容
