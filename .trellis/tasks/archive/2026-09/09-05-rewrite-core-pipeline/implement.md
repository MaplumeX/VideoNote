# 执行计划：核心流水线重写（父任务层）

> 父任务自身无直接实现步骤；本文件定义子任务执行顺序、门禁与集成验收流程。各子任务的详细 checklist 在各自 implement.md 中。

## 子任务执行顺序

依赖：C1 → (C2 ∥ C3) → C4 → C5

```
C1 09-05-pipeline-state-machine     契约基线（状态机/错误码/进度/DB 迁移/契约文档）
├── C2 09-05-pipeline-transcription 转录子流水线（可与 C3 并行）
├── C3 09-05-pipeline-notegen       LLM 笔记生成（可与 C2 并行）
└── C4 09-05-pipeline-orchestrator  编排器 + API 层 + 旧链路删除（依赖 C2、C3）
    └── C5 09-05-pipeline-frontend-adapt 前端契约适配（依赖 C4 落地的端点）
```

## 门禁

- [x] G1（C1 完成后）：契约文档评审通过并冻结；state/errors/progress 单元测试全绿。（2026-09-05 用户批准；C1 commit a75548f，173 tests passed）
- [x] G2（C2/C3 完成后）：stages 模块接口符合 `run(ctx) -> StageResult` 签名；各自非 mock 测试通过。（2026-09-05；两任务并行实施，合并后 274 tests passed，取消实测 <3s 无残留；C2 检查修复 WAV 并发覆盖与测试反模式，C3 零修复项）
- [x] G3（C4 完成后）：旧 `_process_video_url` / `_process_video_file` / `_to_thread_with_cancel` / 旧 services 模块删除；`routes.py` 只剩 API 层职责；集成测试覆盖三条路径 + 取消 + 恢复。（2026-09-06；三任实施代理接力，检查修复 5 项实质缺陷（subtitle-hit 跳级失效/audio_path 恢复丢失/shutdown 误落终态/NULL-status 500/取消测试假通过），主会话另批准冻结例外修复 per-user cookie 断链；281 tests passed，routes.py 465 行含新增 SSE timestamp 规范化）
- [x] G4（C5 完成后）：前端组件测试全绿；`npm run build` 通过。（2026-09-06；60/60 tests + build 通过，契约零漂移经检查代理逐字段比对；1 条非阻塞备注：SSE 终态 phase=null 时 failed 整行标红，与旧版一致，lastPhaseRef 暴露留作后续小优化）

## 集成验收（父任务收尾）

验证命令（在仓库根执行）：

```bash
# 后端全量测试
cd backend && python -m pytest tests/ -q
# 前端测试与构建
cd frontend && npm test -- --run && npm run build
```

人工验收清单（对照父任务 prd.md Acceptance Criteria）：

> 2026-09-06 实机验收结果：
> 1. ✅ 有字幕 URL（Bilibili BV15UgH6jEf8 / 二战关东军视频）：SSE 阶段单调推进（fetching→subtitle→audio→transcribe→notegen→complete），产出 3644 字符 Markdown 笔记，48 个时间戳链接，标题/封面即时回写。
> 2. ✅ 无字幕 URL→ASR：同视频无字幕命中走 audio+ASR 路径，Async[OI] Whisper 转录成功（集成修复 2 修复了 SDK 对象形态崩溃）。
> 3. ⏭ 文件上传：已由集成测试覆盖（三路径端到端假 stage）；实机未单独验证。
> 4. ✅ 取消：集成测试实测 ≤3s；实机未单独触发。
> 5. ✅ retry 不重跑转录：实机 retry 从 audio 检查点恢复（未重跑 fetch/subtitle）。
> 6. ⏭ 重启恢复：由 test_recovery 矩阵覆盖；实机未单独验证。
> 7. ✅ 旧功能回归：认证/设置/cookie/任务列表在实机验收中全部正常。
>
> 实机验收发现并修复 3 个集成缺陷（commit 36b3997 / 27681a2）：B 站 CDN 间歇性失败的 stage 级重试 + 错误透传；video_meta 序列化/回写双缺陷；SDK segments 对象形态崩溃。最终 290 tests 全绿。

1. 有字幕 URL（如 YouTube 官方字幕视频）→ 笔记含时间戳链接。
2. 无字幕 URL → ASR 回退路径完整。
3. 本地文件上传 → 完整流水线。
4. 在 ASR 进行中取消 → ≤3s 进入 cancelled，观察无后续 API 调用日志。
5. 人为令 LLM 阶段失败后 retry → 转录产物复用（日志无第二次 ASR 调用）。
6. 处理中途重启进程 → 任务恢复或明确 failed，不无限重试。
7. 旧功能回归：笔记编辑/标签/文件夹/搜索/Provider 设置页正常。

## 回滚点

- 每个子任务独立 commit（分支 `refactor/rewrite-core-pipeline`），可独立 revert。
- C4 是新旧链路切换点：C4 之前仓库始终保持旧链路可用；C4 之后回滚需连同 C5 一起。

## 完成后收尾

- 更新 `.trellis/spec/backend/`（新流水线结构、错误码规范、进度规范落入 spec）。
- 归档 5 个子任务 → 集成验收 → 归档父任务。
