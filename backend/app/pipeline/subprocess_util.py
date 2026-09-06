"""Managed subprocess execution for yt-dlp / ffmpeg plus shared yt-dlp argv building.

Semantics migrated from the legacy chain (``app/services/subtitle.py``'s
``_ydl_opts`` / ``_parse_cookies_from_browser`` / ``classify_ytdlp_error`` and
the blocking subprocess handling in ``app/services/{audio,transcribe}.py``):

- subprocesses are spawned with ``create_subprocess_exec`` (list args, no shell);
- cancellation (``asyncio.CancelledError``) and timeout both terminate the
  process first and ``kill`` it after a grace period, so no process leaks;
- a cancel handle is registered with the orchestrator so an external cancel
  request terminates the in-flight subprocess immediately.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.config import YT_DLP_COOKIES_FILE, YT_DLP_COOKIES_FROM_BROWSER, YT_DLP_PROXY
from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import CancelHandleRegistrar

# Binary names — module-level so tests can point them at stub scripts.
YT_DLP_BIN = "yt-dlp"
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

# Grace period between SIGTERM and SIGKILL when terminating a subprocess.
KILL_GRACE_SECONDS = 5.0


@dataclass(frozen=True)
class ProcessResult:
    """Completed subprocess outcome."""

    returncode: int
    stdout: str
    stderr: str


async def run_managed_process(
    args: Sequence[str],
    *,
    register_cancel: CancelHandleRegistrar,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
    kill_grace: float = KILL_GRACE_SECONDS,
) -> ProcessResult:
    """Run a subprocess to completion with cancellation- and timeout-safe kill.

    - A cancel handle is registered with the orchestrator: it terminates the
      process immediately and escalates to ``kill`` after ``kill_grace`` seconds.
    - ``asyncio.CancelledError``: terminate -> wait grace -> kill -> re-raise.
    - ``timeout`` expiry: terminate -> wait grace -> kill -> ``PipelineError``.

    In every path the process is fully reaped before returning or raising, so
    cancelled calls never leak a running or zombie process.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=dict(env) if env is not None else None,
    )
    loop = asyncio.get_running_loop()

    def _terminate() -> None:
        if proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

    def _kill() -> None:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    async def _terminate_and_reap() -> None:
        _terminate()
        try:
            await asyncio.wait_for(proc.wait(), kill_grace)
        except TimeoutError:
            _kill()
            await proc.wait()

    def _cancel_handle() -> None:
        # Invoked (synchronously) by the orchestrator on cancel: terminate now,
        # escalate to kill after the grace period.
        _terminate()
        loop.call_later(kill_grace, _kill)

    register_cancel(_cancel_handle)
    try:
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            await _terminate_and_reap()
            raise PipelineError(
                ErrorCode.PROCESSING_FAILED,
                detail=f"process timed out after {timeout}s: {args[0]}",
            ) from None
        except asyncio.CancelledError:
            await _terminate_and_reap()
            raise
        returncode = proc.returncode if proc.returncode is not None else -1
        return ProcessResult(
            returncode=returncode,
            stdout=stdout_b.decode("utf-8", "replace"),
            stderr=stderr_b.decode("utf-8", "replace"),
        )
    finally:
        register_cancel(None)


def parse_cookies_from_browser(
    value: str,
) -> tuple[str, str | None, str | None, str | None]:
    """Parse ``YT_DLP_COOKIES_FROM_BROWSER`` syntax (migrated verbatim).

    Returns ``(browser_name, profile, keyring, container)``; raises ``ValueError``
    on invalid syntax. Supports ``BROWSER[+KEYRING][:PROFILE][::CONTAINER]``.
    """
    mobj = re.fullmatch(
        r"""(?x)
        (?P<name>[^+:]+)
        (?:\s*\+\s*(?P<keyring>[^:]+))?
        (?:\s*:\s*(?!:)(?P<profile>.+?))?
        (?:\s*::\s*(?P<container>.+))?
        """,
        value,
    )
    if mobj is None:
        raise ValueError(f"Invalid YT_DLP_COOKIES_FROM_BROWSER value: {value}")

    browser_name, keyring, profile, container = mobj.group(
        "name", "keyring", "profile", "container"
    )
    return browser_name.lower(), profile, keyring.upper() if keyring else None, container


def _cookies_from_browser_spec(value: str) -> str:
    """Reconstruct the CLI ``--cookies-from-browser`` spec from the config value."""
    name, profile, keyring, container = parse_cookies_from_browser(value)
    spec = name
    if keyring:
        spec += f"+{keyring}"
    if profile:
        spec += f":{profile}"
    if container:
        spec += f"::{container}"
    return spec


def build_ytdlp_args(
    task_args: Sequence[str],
    *,
    cookiefile_path: str | None = None,
    quiet: bool = True,
) -> list[str]:
    """Build a yt-dlp CLI argv with the shared global options (legacy ``_ydl_opts``).

    Global options: no-warnings, remote EJS components, proxy, cookies. Cookie
    priority mirrors the legacy semantics: per-user cookie file > cookies from
    browser > cookies file from config. ``task_args`` carries the call-specific
    options and the URL.
    """
    argv: list[str] = [YT_DLP_BIN]
    if quiet:
        argv.append("--quiet")
    argv += ["--no-warnings", "--remote-components", "ejs:github"]
    if YT_DLP_PROXY:
        argv += ["--proxy", YT_DLP_PROXY]
    if cookiefile_path:
        argv += ["--cookies", cookiefile_path]
    else:
        if YT_DLP_COOKIES_FROM_BROWSER:
            argv += [
                "--cookies-from-browser",
                _cookies_from_browser_spec(YT_DLP_COOKIES_FROM_BROWSER),
            ]
        if YT_DLP_COOKIES_FILE:
            argv += ["--cookies", YT_DLP_COOKIES_FILE]
    argv += list(task_args)
    return argv


def classify_ytdlp_error(text: str) -> ErrorCode:
    """Map a yt-dlp error message to a stable error code (keyword table migrated).

    Keywords are checked case-insensitively against the legacy table in
    ``.trellis/spec/backend/error-handling.md``.
    """
    msg = text.lower()
    if "private" in msg or "login required" in msg:
        return ErrorCode.VIDEO_PRIVATE
    if "geo" in msg or "not available in your country" in msg or "region" in msg:
        return ErrorCode.VIDEO_GEO_RESTRICTED
    if "404" in msg or "not found" in msg or "unavailable" in msg or "deleted" in msg:
        return ErrorCode.VIDEO_NOT_FOUND
    if "cookie" in msg or ("login" in msg and "required" in msg):
        return ErrorCode.VIDEO_COOKIE_INVALID
    return ErrorCode.VIDEO_FETCH_FAILED
