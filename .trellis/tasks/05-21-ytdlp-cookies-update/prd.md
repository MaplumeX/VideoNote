# Support yt-dlp Cookies and Stable Updates

## Goal

Allow VideoNote backend yt-dlp calls to use authenticated browser cookies or a cookies file so YouTube videos that require "Sign in to confirm you're not a bot" can be processed, and update the locked yt-dlp dependency to the latest stable release available to the package manager.

## What I Already Know

* The user saw yt-dlp fail on YouTube with "Sign in to confirm you're not a bot."
* The user wants to solve this with option 1 (cookies) and option 2 (update yt-dlp).
* Audio download uses `download_audio_via_ytdlp` in `backend/app/services/audio.py`.
* Subtitle/title/metadata extraction also uses yt-dlp through `_ydl_opts` in `backend/app/services/subtitle.py`.
* Existing yt-dlp configuration supports `YT_DLP_PROXY` from `backend/app/config.py`.
* Backend dependencies are managed by `backend/pyproject.toml` and `backend/uv.lock`.

## Assumptions

* Configure cookies through environment variables rather than hardcoding local machine paths.
* Support both browser cookie extraction and explicit cookies file paths.
* Prefer latest stable `yt-dlp` from PyPI over nightly/dev builds.

## Requirements

* Add backend configuration for `YT_DLP_COOKIES_FROM_BROWSER`.
* Add backend configuration for `YT_DLP_COOKIES_FILE`.
* Apply these options to all yt-dlp calls through the shared `_ydl_opts` helper.
* Document the new environment variables in `.env.example`.
* Upgrade `yt-dlp` in the lockfile using the package manager.

## Acceptance Criteria

* [ ] `download_audio_via_ytdlp`, subtitle extraction, title lookup, and metadata lookup all inherit configured cookies.
* [ ] Existing proxy behavior remains unchanged.
* [ ] `.env.example` shows how to configure Chrome cookies or a cookies file.
* [ ] `backend/uv.lock` resolves a newer stable yt-dlp version.
* [ ] Backend lint passes.

## Definition of Done

* Tests added or updated where practical.
* Lint/typecheck or equivalent backend quality checks run.
* Behavior changes documented in env example.
* No unrelated files modified.

## Out of Scope

* UI for uploading cookies.
* Persisting cookies in the database.
* Bypassing YouTube access controls beyond using the user's authenticated cookies.
* Switching to yt-dlp nightly/dev releases.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/index.md`, `.trellis/spec/backend/error-handling.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/backend/logging-guidelines.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
* PyPI notes: yt-dlp publishes stable releases and also development/nightly releases. The stable package should be sufficient for this task.
