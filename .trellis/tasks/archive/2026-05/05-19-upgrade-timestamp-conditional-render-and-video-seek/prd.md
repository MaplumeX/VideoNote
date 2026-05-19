# 升级时间戳功能：条件渲染 + 视频跳转

## Goal

让时间戳更智能：转录数据无时间戳时不强制添加；有时间戳时点击可跳转到视频对应位置。

## Decisions

* **MVP 只支持 URL 来源视频跳转**（YouTube/Bilibili iframe 嵌入）。上传文件来源无视频可播（文件已被删除），不做保留文件的视频服务。
* **视频播放器为悬浮窗口**：拖拽移动 + 缩放大小 + 最小化/关闭；首次出现在右下角；有视频 URL 时在 sidebar 底部显示"播放"入口按钮，点击弹出悬浮窗；点击时间戳时，若播放器已打开则 seek，未打开则先打开再 seek。

## Requirements

* 1. 条件渲染：transcript 无时间戳时，LLM prompt 不要求保留时间戳
* 2. 条件渲染：前端 remark 插件只在有 `#t=` 链接时生成 timestamp-badge（当前已如此）
* 3. 悬浮视频播放器：URL 来源笔记在 sidebar 底部显示"播放"按钮，点击弹出可拖拽/缩放/最小化/关闭的 iframe 悬浮窗
* 4. 点击时间戳跳转：播放器已打开 → seek 到秒数；未打开 → 先打开再 seek
* 5. 无视频 URL 的笔记：时间戳 badge 不可点击，视觉灰显区分；不显示播放按钮和播放器

## Acceptance Criteria

* [ ] SiliconFlow/无 segment 的 transcript 生成笔记时，不包含虚假时间戳
* [ ] YouTube 来源笔记，点击时间戳 → YouTube iframe seek 到对应秒数
* [ ] Bilibili 来源笔记，点击时间戳 → Bilibili iframe seek 到对应秒数
* [ ] 无视频 URL 的笔记，时间戳 badge 灰显不可点击
* [ ] 无视频 URL 的笔记，不显示播放按钮和悬浮窗
* [ ] 悬浮窗可拖拽、可缩放、可最小化/关闭
* [ ] 点击时间戳时播放器未打开 → 自动打开并 seek

## Definition of Done

* Lint / typecheck 通过
* 前端构建无报错
* 手动验证时间戳点击跳转

## Out of Scope

* 上传文件的视频播放（文件已被删除，需保留文件+视频服务端点）
* 视频播放器 UI 样式深度定制
* 时间戳自动同步（视频播放时自动高亮当前时间戳）

## Technical Approach

### 后端：条件化 LLM prompt

* `transcribe.py` 返回 transcript 后，检测是否包含 `#t=` 时间戳标记
* 将检测结果传给 `note_gen.py`
* `note_gen.py` 的 prompt 根据有无时间戳，条件性加入"保留时间戳"的指令

### 前端：悬浮视频播放器

* 新建 `VideoPlayerFloat` 组件：iframe 嵌入 YouTube/Bilibili，支持拖拽/缩放/最小化/关闭
* YouTube iframe seek: `https://www.youtube.com/embed/{videoId}?start={seconds}&autoplay=1`
* Bilibili iframe seek: `https://player.bilibili.com/player.html?bvid={bvid}&page=1&high_quality=1&start={seconds}`
* 在 `NoteDetailPage` 中根据 `video_url` + `platform` 判断是否显示播放入口

### 前端：时间戳 badge 条件样式

* `TimestampBadgeView` 需要知道当前笔记是否有视频 URL
* 通过 React context 或 callback 传递 `onTimestampClick(seconds)` 和 `hasVideo` 状态
* 有视频时：badge 可点击样式 + click handler
* 无视频时：badge 灰显 + cursor-default

### 数据流

* `NoteDetailPage` 已有 `video_url` 和 `platform`（通过 `fetchTaskById`）
* 需将 `video_url` / `platform` 传给 `NoteEditor` → `TimestampBadgeView`

## Technical Notes

* `NoteEditor.tsx`: timestamp-badge node + TimestampBadgeView + remarkTimestampBadge
* `note_gen.py`: LLM prompt（需条件化时间戳指令）
* `transcribe.py`: SiliconFlow 不返回 segments，OpenAI Whisper 可能也不返回
* `routes.py`: `_process_video_file` 在处理完后删除文件
* `NoteDetailPage.tsx`: 三栏布局（左 sidebar / 中 editor / 右 TOC）
