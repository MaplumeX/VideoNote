# Fix: SSE event parsing fails on CRLF line endings

## Problem
After submitting a video, the content area shows a white screen. The root cause is in `useSSE.ts:53`: the SSE event boundary check `line === ""` fails because `sse-starlette` uses `\r\n` as the default line separator. When the frontend splits the buffer by `\n`, empty event-boundary lines become `"\r"` instead of `""`, so no SSE events are ever parsed.

## Fix
Change the empty-line check in `useSSE.ts` from `line === ""` to `line.trim() === ""` so it correctly detects event boundaries regardless of `\r\n`, `\n`, or `\r` line endings.

## Files
- `frontend/src/hooks/useSSE.ts` — line 53

## Acceptance
- SSE progress events are parsed correctly (progress bar updates)
- SSE complete event is parsed correctly (result renders, no white screen)
- Works with both `\r\n` (sse-starlette default) and `\n` line endings
