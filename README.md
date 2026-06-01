# VideoNote

VideoNote 是一个面向视频学习和知识整理的 AI 笔记工具。它可以从 YouTube、Bilibili 视频链接或本地视频文件中提取字幕/音频，调用 ASR 与 LLM 生成结构化 Markdown 笔记，并提供账号、历史记录、标签、文件夹、收藏和在线编辑能力。

## 功能特性

- 视频链接生成笔记：支持 YouTube 与 Bilibili 链接。
- 本地视频上传：支持常见视频格式，默认最大 500MB。
- 字幕优先策略：优先提取视频字幕；没有字幕时下载/抽取音频并转写。
- 多模型配置：ASR 与 LLM 可分别配置 API Key、API Base 和模型。
- 实时进度：通过 SSE 返回下载、转写、生成等阶段进度。
- 笔记管理：支持历史记录、搜索、分页、标签、文件夹、收藏和批量操作。
- Markdown 编辑：前端使用 Milkdown，支持 GFM、代码高亮、KaTeX 和 Mermaid。
- 账号系统：邮箱注册/登录，访问令牌与刷新令牌机制。
- 平台 Cookie：支持为 YouTube、Bilibili 保存用户级 cookies，提高受限视频访问能力。
- Docker 部署：提供前后端镜像构建与 Nginx 反向代理配置。

## 技术栈

### 前端

- React 19
- TypeScript
- Vite 6
- Tailwind CSS 4
- React Router 7
- Milkdown
- i18next
- lucide-react

### 后端

- Python 3.11+
- FastAPI
- SQLite + aiosqlite
- yt-dlp
- FFmpeg
- OpenAI SDK 兼容接口
- SSE Starlette
- PyJWT / bcrypt / cryptography

## 项目结构

```text
.
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/          # API 路由：认证、视频处理、笔记管理、Cookie 管理
│   │   ├── services/     # 音频、字幕、转写、笔记生成、Markdown 处理
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── db.py
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/             # React 前端
│   ├── src/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── components/
│   │   ├── i18n/
│   │   └── pages/
│   ├── package.json
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 环境要求

本地开发需要：

- Node.js 22 或兼容版本
- Python 3.11+
- uv
- FFmpeg
- 可用的 ASR/LLM API Key

Docker 部署需要：

- Docker
- Docker Compose

## 配置环境变量

先从示例文件创建 `.env`：

```bash
cp .env.example .env
```

最少需要配置：

```bash
OPENAI_API_KEY=sk-...
SECRET_KEY=your-stable-secret-key-here
```

常用变量：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `OPENAI_API_KEY` | ASR 与 LLM 的默认 API Key | 空 |
| `ASR_PROVIDER` | ASR 提供商 | `openai` |
| `ASR_API_KEY` | ASR API Key，空时使用 `OPENAI_API_KEY` | 空 |
| `ASR_API_BASE` | ASR API Base | `https://api.openai.com/v1` |
| `ASR_MODEL` | ASR 模型 | `whisper-1` |
| `LLM_API_KEY` | LLM API Key，空时使用 `OPENAI_API_KEY` | 空 |
| `LLM_API_BASE` | LLM API Base | `https://api.openai.com/v1` |
| `LLM_MODEL` | LLM 模型 | `gpt-4o` |
| `YT_DLP_PROXY` | yt-dlp 代理，例如 `http://127.0.0.1:7890` | 空 |
| `YT_DLP_COOKIES_FROM_BROWSER` | 从浏览器读取 cookies，例如 `chrome` | 空 |
| `YT_DLP_COOKIES_FILE` | Netscape cookies.txt 文件路径 | 空 |
| `UPLOAD_DIR` | 上传文件、缩略图和数据库相关数据目录 | `/tmp/videonote_uploads` |
| `MAX_UPLOAD_SIZE_MB` | 最大上传视频大小 | `500` |
| `SECRET_KEY` | JWT 签名与敏感配置加密使用的稳定密钥 | 自动生成 |
| `FRONTEND_URL` | 后端允许的前端 CORS 来源 | `http://localhost:5173` |

生产或 Docker 部署时必须显式设置稳定的 `SECRET_KEY`。如果让后端自动生成，容器重启后旧的加密 API Key 可能无法解密。

## 使用 Docker 运行

1. 准备 `.env`：

```bash
cp .env.example .env
```

2. 修改 `.env` 中的关键配置：

```bash
OPENAI_API_KEY=sk-...
SECRET_KEY=your-stable-secret-key-here
FRONTEND_URL=http://localhost
UPLOAD_DIR=/data/videonote
```

3. 启动服务：

```bash
docker compose up --build
```

4. 打开：

```text
http://localhost
```

Docker 模式下，前端由 Nginx 提供静态资源，并将 `/api/` 代理到后端 `backend:8000`。

## 本地开发

### 1. 启动后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端健康检查：

```bash
curl http://localhost:8000/api/health
```

### 2. 启动前端

另开一个终端：

```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://localhost:5173
```

Vite 开发服务器会把 `/api` 代理到 `http://localhost:8000`。

## 常用命令

### 前端

```bash
cd frontend
npm run dev       # 启动开发服务器
npm run build     # 类型检查并构建生产产物
npm run preview   # 预览生产构建
npm run lint      # 运行 ESLint
```

### 后端

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uv run pytest
uv run ruff check .
```

## API 概览

所有业务接口默认挂载在 `/api` 下：

- `GET /api/health`：健康检查。
- `POST /api/auth/register`：注册。
- `POST /api/auth/login`：登录。
- `POST /api/auth/refresh`：刷新访问令牌。
- `POST /api/auth/logout`：退出登录。
- `GET /api/auth/me`：当前用户信息。
- `POST /api/process`：提交视频链接生成笔记。
- `POST /api/upload`：上传本地视频生成笔记。
- `GET /api/tasks/{job_id}/progress`：SSE 实时任务进度。
- `GET /api/tasks/{job_id}/result`：获取生成结果。
- `GET /api/tasks`：分页查询笔记任务。
- `PUT /api/tasks/{job_id}/content`：更新笔记 Markdown 内容。
- `POST /api/tasks/{job_id}/retry`：重试失败的 URL 任务。
- `GET /api/tags` / `POST /api/tags`：标签列表与创建。
- `GET /api/folders` / `POST /api/folders`：文件夹列表与创建。
- `PUT /api/cookies/{platform}`：保存平台 Cookie，`platform` 支持 `youtube`、`bilibili`。
- `GET /api/providers`、`GET /api/settings`、`PUT /api/settings`、`POST /api/models`：模型提供商与用户设置。

## 使用流程

1. 注册或登录账号。
2. 在设置页配置 ASR 与 LLM 的 API Key、API Base 和模型。
3. 如需访问受限视频，在设置页保存 YouTube 或 Bilibili cookies。
4. 新建笔记，粘贴视频链接或上传本地视频。
5. 等待任务进度完成后，在详情页查看和编辑生成的 Markdown 笔记。
6. 使用标签、文件夹、收藏和搜索整理历史笔记。

## 注意事项

- URL 处理当前只接受 YouTube 与 Bilibili 平台。
- 本地视频上传会在处理完成后清理原始上传临时文件。
- 如果视频没有可用字幕，后端会依赖 FFmpeg 抽取音频并调用 ASR。
- Docker 部署时 `FRONTEND_URL` 应设置为实际访问前端的 Origin，例如 `https://note.example.com`。
- Cookie 内容会按用户加密保存，但仍应避免提交真实 `.env`、cookies 或数据库文件到版本库。
