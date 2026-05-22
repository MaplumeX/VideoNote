# 支持上传Cookie

## Goal

允许用户通过前端 UI 上传视频平台 Cookie（如 YouTube、Bilibili），使 yt-dlp 能够访问需要登录的视频内容，替代当前仅支持环境变量配置的方式。

## What I already know

* 当前 yt-dlp Cookie 配置仅支持环境变量：`YT_DLP_COOKIES_FROM_BROWSER` 和 `YT_DLP_COOKIES_FILE`（全局、服务端）
* 前一个 task（05-21-ytdlp-cookies-update）已实现环境变量 Cookie 支持，明确将"UI 上传 Cookie"和"数据库持久化 Cookie"列为 Out of Scope
* 项目已有 per-user 加密配置模式：`user_providers` 表使用 Fernet 加密 API Key
* Settings 页面已有 Provider 配置卡片（ASR、LLM），Cookie 管理自然适合作为新的 Settings 区域
* Bilibili 视频可能需要登录 Cookie 才能获取字幕（`need_login_subtitle` 为 True 时）
* YouTube 会出现 "Sign in to confirm you're not a bot" 要求，Cookie 可解决
* yt-dlp 支持 `cookiefile`（Netscape cookies.txt 格式）和 `cookiesfrombrowser`（浏览器提取）两种 Cookie 来源
* 前端已有 `react-dropzone` 依赖，可用于文件上传交互

## Assumptions (temporary)

* Cookie 应该是 per-user 而非全局的（每个用户可能需要不同平台的 Cookie）
* 上传的 Cookie 应该在数据库中加密存储（复用现有 Fernet 加密模式）
* 需要支持 Netscape cookies.txt 格式（yt-dlp 原生支持）

## Open Questions

* ~~Cookie 上传格式：仅 cookies.txt 文件？还是也支持粘贴原始 Cookie 字符串？~~ → 文件上传 + 文本粘贴
* ~~是否需要分平台管理 Cookie（YouTube / Bilibili 分开）？~~ → 分平台管理，YouTube / Bilibili 各自独立
* ~~是否保留现有环境变量 Cookie 配置作为全局 fallback？~~ → 保留 fallback，per-user Cookie 优先，环境变量作为兜底
* ~~Cookie 更新时的验证方式：是否需要"测试连接"功能？~~ → 不需要，上传即保存，用户自行通过处理视频验证

## Requirements (evolving)

* 前端 Settings 页面新增 Cookie 管理区域
* 支持两种 Cookie 输入方式：上传 cookies.txt 文件 + 直接粘贴 Cookie 文本字符串
* 分平台管理：YouTube / Bilibili 各自独立上传和管理 Cookie
* 后端写入时按平台域名过滤 Cookie 条目，确保 YouTube 区只含 `.youtube.com` 域名，Bilibili 同理
* 后端将粘贴的 Cookie 字符串自动转换为 Netscape cookies.txt 格式
* 后端新增 API 端点用于 Cookie 的 CRUD
* Cookie 在数据库中加密存储
* yt-dlp 调用时优先使用用户上传的 Cookie，若该平台无 per-user Cookie 则 fallback 到环境变量配置

## Acceptance Criteria (evolving)

* [ ] 用户可以在 Settings 页面分平台（YouTube / Bilibili）上传 Cookie 文件或粘贴 Cookie 文本
* [ ] 上传的 Cookie 被加密存储到数据库
* [ ] yt-dlp 处理视频时使用用户上传的 Cookie
* [ ] 现有环境变量 Cookie 配置仍可作为 fallback

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* i18n key 添加完整（中英文）
* Docs/notes updated if behavior changes

## Out of Scope (explicit)

* 浏览器 Cookie 自动提取（cookiesfrombrowser）— 这是环境变量层面的配置
* Cookie 的自动刷新/续期
* 支持非 Netscape cookies.txt 格式
* Cookie 有效性测试/验证功能
* Cookie 上次更新时间展示
* YouTube + Bilibili 之外的平台支持（未来可扩展）

## Technical Notes

* 相关文件：`backend/app/services/subtitle.py`（_ydl_opts）、`backend/app/db.py`（user_providers 表模式）、`backend/app/crypto.py`（Fernet 加密）、`frontend/src/pages/SettingsPage.tsx`
* 前端已有 react-dropzone 依赖
* yt-dlp 的 cookiefile 参数接收 Netscape cookies.txt 文件路径
