# Support Docker Deployment

## Goal

让 VideoNote 项目支持 Docker 一键部署，用户无需手动安装 Python、Node.js、ffmpeg 等依赖，通过 `docker compose up` 即可运行完整服务。

## Requirements

* 双容器架构：nginx 容器（serve 前端 + 反向代理 /api）+ 后端容器（FastAPI/uvicorn）
* 前端使用 multi-stage 构建：构建阶段编译 React SPA，运行阶段仅 nginx + 静态文件
* 后端使用 multi-stage 构建：构建阶段安装依赖，运行阶段精简镜像
* nginx 正确配置：serve 前端静态文件、代理 /api 到后端、SSE 长连接支持（proxy_buffering off）
* SQLite 数据持久化：UPLOAD_DIR 通过 volume mount 持久化
* 关键环境变量可配置：SECRET_KEY、API keys、proxy 等
* 仅 HTTP，HTTPS 由外部网关（Cloudflare/Nginx Proxy Manager 等）处理

## Acceptance Criteria

* [ ] `docker compose up` 后服务可正常访问（默认端口 80）
* [ ] 前端页面可正常加载
* [ ] API 请求（注册、登录、视频处理等）正常工作
* [ ] SSE 实时进度推送正常
* [ ] 容器重启后数据不丢失（SQLite 数据库、上传文件）
* [ ] SECRET_KEY 等关键环境变量可通过 .env 文件配置

## Definition of Done

* backend/Dockerfile、frontend/Dockerfile、docker-compose.yml、nginx.conf、.dockerignore 已创建
* .env.example 更新 Docker 相关配置说明
* 本地 `docker compose up` 测试通过

## Decision (ADR-lite)

**Context**: 需要选择容器架构和部署模式
**Decision**: 双容器（nginx + backend），仅 HTTP，生产部署最小可用
**Consequences**: 职责清晰、可独立扩容后端；后续可加 dev compose、健康检查、非 root 用户等

## Out of Scope

* HTTPS / Let's Encrypt 支持
* 开发模式 compose（热重载）
* 健康检查 endpoint
* 非 root 用户运行
* 多后端负载均衡
* CI/CD 集成

## Technical Notes

* 后端入口：uvicorn app.main:app，默认端口 8000
* 前端构建产物：frontend/dist/
* SQLite 数据库路径：{UPLOAD_DIR}/videonote.db
* SSE 端点需 nginx proxy_buffering off + proxy_read_timeout 调大
* SECRET_KEY 必须稳定（否则已加密的 API key 不可恢复），.env.example 中应标注必填
* yt-dlp 下载大文件可能需较长时间，nginx proxy_read_timeout 需调大
* nginx 需处理客户端大文件上传（client_max_body_size 需匹配 MAX_UPLOAD_SIZE_MB）
