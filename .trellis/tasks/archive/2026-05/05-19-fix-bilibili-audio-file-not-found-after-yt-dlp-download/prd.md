# Fix Bilibili audio file not found after yt-dlp download

## Goal

修复 yt-dlp 下载 Bilibili 视频音频后的 FileNotFoundError，使 Bilibili 和 YouTube 均正常工作。

## Requirements

- 检查 `ydl.download()` 返回值（0=成功，非0=有错误），非零时抛出明确异常
- 扩展文件查找逻辑：除 `audio.*` 外，也匹配无扩展名的 `audio` 文件
- 添加下载后目录内容的 info 级别日志，方便排查
- `quiet=True` 改为仅在非错误输出上静默，让错误信息能被捕获

## Acceptance Criteria

- [ ] Bilibili 视频提交后不再抛 FileNotFoundError
- [ ] YouTube 视频仍然正常工作
- [ ] 下载失败时日志包含目录内容和 yt-dlp 返回码
- [ ] lint / typecheck green

## Out of Scope

- 修改 yt-dlp format/outtmpl 配置
- 添加 Bilibili 专用 extractor 逻辑

## Technical Approach

1. `ydl.download([url])` 返回 `_download_retcode`（0=成功），当前未检查 → 添加返回值检查
2. `glob("audio.*")` 无法匹配无扩展名文件 → 改为 `glob("audio*")` 然后排除 `audio.wav`（转换产物）
3. 下载后添加 `logger.info` 列出目录内容
4. 将 `quiet=True` + `no_warnings=True` 改为仅静默常规输出，保留错误信息

## Technical Notes

- 关键文件：`backend/app/services/audio.py`（`download_audio_via_ytdlp` 函数，第35-69行）
- `_ydl_opts` 来自 `backend/app/services/subtitle.py`，设置了 `quiet=True, no_warnings=True`
- `ydl.download()` 返回值：0=全部成功，非0=有下载错误
- Bilibili 有独立音频流（m4a），`bestaudio` 理论上可行，问题更可能是 yt-dlp 静默失败未被捕获
- `extract_audio()` 函数用于将非 WAV 文件转换为 WAV
