# VideoNote

> 将任意视频转化为结构化 Markdown 笔记 —— 带可点击时间戳、所见即所得编辑与完整笔记管理。

[English](README.md) · [简体中文](README.zh-CN.md)

VideoNote 接收视频链接（YouTube / Bilibili）或上传的本地视频文件，提取字幕（无字幕时回退为 ASR 转录），并用 LLM 生成结构良好的 Markdown 笔记，内含可点击的时间戳链接。笔记可在所见即所得的 Markdown 编辑器中编辑，并支持文件夹、标签、收藏与搜索管理。

---

## 功能特性

- **两种输入方式** —— 提交视频链接（YouTube / Bilibili）或上传本地视频文件。
- **智能转录流水线** —— 优先使用已有字幕；无字幕时回退为音频提取（`ffmpeg`）+ ASR 转录。
- **LLM 笔记生成** —— 产出结构化 Markdown，含标题层级、要点列表、分段摘要，以及可点击的 `[HH:MM:SS](#t=SECONDS)` 时间戳。
- **实时进度** —— 通过 SSE（Server-Sent Events）将阶段与进度推送到前端。
- **所见即所得编辑器** —— [Milkdown](https://milkdown.dev/) 编辑器，支持 GFM、KaTeX 数学公式、Mermaid 图表与 Prism 代码高亮。
- **笔记管理** —— 文件夹树、标签、收藏、批量操作、全文搜索与分页。
- **用户级 Provider 配置** —— ASR 与 LLM 可独立配置（OpenAI、SiliconFlow、DeepSeek 或任意 OpenAI 兼容端点）。API Key 加密存储。
- **Cookie 管理** —— 按用户配置 YouTube / Bilibili 的 Cookie，访问会员专享或地区受限内容。
- **身份认证** —— 基于 JWT 的用户账户，含刷新令牌与 bcrypt 密码哈希。
- **双语界面** —— 英语与 简体中文，自动检测。
- **单镜像部署** —— Vite SPA 打包进 FastAPI 运行镜像，无需 nginx 或 supervisord。

## 技术栈

| 层级   | 技术栈                                                                                          |
| ------ | ----------------------------------------------------------------------------------------------- |
| 后端   | Python 3.11 · FastAPI · asyncio · aiosqlite · yt-dlp · ffmpeg · OpenAI SDK · PyJWT · bcrypt     |
| 前端   | React 19 · Vite · TypeScript · TailwindCSS v4 · shadcn/ui · Milkdown · i18next · React Router   |
| 基础设施 | 多阶段构建的单 Docker 镜像，发布至 GHCR · docker-compose                                       |

## 快速开始（Docker）

镜像发布在 GitHub Container Registry：

```bash
docker pull ghcr.io/maplumex/videonote:latest
```

### 一键部署

只需一条命令拉取 compose 文件和 env 模板、生成稳定密钥并启动：

```bash
# 1. 下载 docker-compose.yml 与 .env 模板
curl -fsSL https://raw.githubusercontent.com/MaplumeX/VideoNote/main/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/MaplumeX/VideoNote/main/.env.example -o .env

# 2. 设置必填项：部署地址与稳定密钥
echo "FRONTEND_URL=http://localhost" >> .env
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 3.（可选）填入 OpenAI Key，或之后在界面里按用户配置 provider
echo "OPENAI_API_KEY=sk-..." >> .env

# 4. 启动
docker compose up -d
```

然后打开 <http://localhost:8965>，注册账号，在 **设置** 中配置你的 ASR / LLM provider。

### 手动部署

1. 将 `.env.example` 复制为 `.env` 并填写密钥：

   ```bash
   cp .env.example .env
   ```

   Docker 部署必须配置：

   ```dotenv
   # 设为你部署后的访问地址（例如 https://note.example.com）
   FRONTEND_URL=http://localhost

   # 一个稳定的密钥 —— 自动生成的密钥在容器重启后会丢失，
   # 这会导致已加密的 API Key 无法解密恢复。
   SECRET_KEY=<你的稳定密钥>
   ```

2. 使用 `docker compose` 启动：

   ```bash
   docker compose up -d
   ```

3. 打开 <http://localhost:8965>，注册账号，在 **设置** 中配置你的 ASR / LLM provider。

### 环境变量

| 变量                           | 说明                                                       | 默认值                         |
| ------------------------------ | --------------------------------------------------------- | ------------------------------ |
| `OPENAI_API_KEY`               | 当用户未单独配置时，ASR/LLM 的回退 Key                       | —                              |
| `ASR_PROVIDER`                 | `openai` 或 `siliconflow`                                 | `openai`                       |
| `ASR_API_BASE`                 | ASR 端点                                                   | `https://api.openai.com/v1`    |
| `ASR_MODEL`                    | ASR 模型（如 `whisper-1`、`FunAudioLLM/SenseVoiceSmall`）  | `whisper-1`                    |
| `LLM_API_BASE`                 | LLM 端点                                                   | `https://api.openai.com/v1`    |
| `LLM_MODEL`                    | LLM 模型（如 `gpt-4o`、`deepseek-chat`）                   | `gpt-4o`                       |
| `YT_DLP_PROXY`                 | yt-dlp 代理（用于访问 YouTube 等）                          | —                              |
| `YT_DLP_COOKIES_FROM_BROWSER`  | 从浏览器 profile 读取 yt-dlp Cookie（如 `chrome`）           | —                              |
| `YT_DLP_COOKIES_FILE`          | Netscape 格式 `cookies.txt` 文件路径                         | —                              |
| `UPLOAD_DIR`                   | 上传文件与缩略图存放目录                                    | `/tmp/videonote_uploads`        |
| `MAX_UPLOAD_SIZE_MB`            | 最大上传大小                                               | `500`                          |
| `SECRET_KEY`                   | JWT 签名密钥（**Docker 中必须显式设置**）                    | 自动生成                       |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | Access token 有效期                                        | `15`                           |
| `REFRESH_TOKEN_EXPIRE_DAYS`    | Refresh token 有效期                                       | `7`                            |
| `FRONTEND_URL`                 | CORS 允许的源（**Docker 部署必填**）                        | `http://localhost:5173`        |
| `FRONTEND_STATIC_DIR`          | 打包前端资源路径（由 Docker 镜像设置）                      | `/app/static`                   |

完整带注释的配置见 [`.env.example`](.env.example)。

## 本地开发

### 前置条件

- Python 3.11+ 与 [`uv`](https://docs.astral.sh/uv/)
- Node.js 22+
- 已安装并在 `PATH` 中的 `ffmpeg`

### 后端

```bash
cd backend
uv sync
cp ../.env.example ../.env   # 然后编辑 .env
uv run uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm ci
npm run dev    # http://localhost:5173
```

前后端分开运行时，在 `.env` 中设置 `FRONTEND_URL=http://localhost:5173`，以便后端允许开发服务器的 CORS 请求。

### 测试与 Lint

```bash
# 后端
cd backend
uv run pytest
uv run ruff check .

# 前端
cd frontend
npm run lint
npm run build
```

## 工作原理

```
链接 / 文件
   │
   ├─ 链接 ──► yt-dlp ──► 获取视频信息与缩略图
   │                       │
   │                       └─► 尝试字幕提取
   │                              │
   │                              └─ 无字幕？ ──► 下载音频 ──► ASR 转录
   │
   └─ 文件 ──► ffmpeg ──► 提取音频 ──► ASR 转录
                                                  │
                                                  └─► LLM 笔记生成 ──► Markdown 笔记
                                                                                     │
                                                                                     └─► 入库，可编辑
```

每个阶段的进度都会通过 SSE 实时推送至客户端。

## 许可证

本项目基于 MIT 协议开源。