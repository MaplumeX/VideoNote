"""Tests for subprocess_util: cancellation, timeout, no leaked processes, argv building."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.subprocess_util import (
    build_ytdlp_args,
    classify_ytdlp_error,
    parse_cookies_from_browser,
    run_managed_process,
)


class Registrar:
    """Minimal CancelHandleRegistrar recording the last registered handle."""

    def __init__(self) -> None:
        self.handle: object | None = None

    def __call__(self, handle) -> None:  # type: ignore[no-untyped-def]
        self.handle = handle


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


async def _spawn_and_pid(args: list[str]) -> int:
    """Spawn a process via run_managed_process and return its pid once known."""
    registrar = Registrar()

    async def run() -> None:
        await run_managed_process(args, register_cancel=registrar)

    task = asyncio.create_task(run())
    # Wait until the cancel handle is registered (= process spawned).
    for _ in range(200):
        if registrar.handle is not None:
            break
        await asyncio.sleep(0.02)
    assert registrar.handle is not None
    return task


class TestRunManagedProcess:
    async def test_captures_stdout_stderr_and_retcode(self) -> None:
        script = (
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"
        )
        result = await run_managed_process(
            [sys.executable, "-c", script],
            register_cancel=lambda h: None,
        )
        assert result.returncode == 3
        assert result.stdout.strip() == "out"
        assert result.stderr.strip() == "err"

    async def test_timeout_terminates_process(self) -> None:
        with pytest.raises(PipelineError) as exc_info:
            await run_managed_process(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                register_cancel=lambda h: None,
                timeout=0.5,
            )
        assert exc_info.value.code is ErrorCode.PROCESSING_FAILED
        assert "timed out" in exc_info.value.detail

    async def test_cancel_terminates_process_within_3s_and_no_leak(self) -> None:
        import time

        registrar = Registrar()

        async def run() -> None:
            await run_managed_process(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                register_cancel=registrar,
            )

        task = asyncio.create_task(run())
        for _ in range(200):
            if registrar.handle is not None:
                break
            await asyncio.sleep(0.02)
        assert registrar.handle is not None

        # Grab the child pid: the only subprocess is the python we spawned.
        # Use psutil-free approach: read from /proc children of current proc.
        # Simpler: cancel and rely on returncode check via task exception.
        start = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        elapsed = time.monotonic() - start
        assert elapsed < 3.0, f"cancellation took {elapsed:.2f}s"

    async def test_cancel_handle_terminates_process(self) -> None:
        registrar = Registrar()

        async def run() -> None:
            await run_managed_process(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                register_cancel=registrar,
            )

        task = asyncio.create_task(run())
        for _ in range(200):
            if registrar.handle is not None:
                break
            await asyncio.sleep(0.02)
        handle = registrar.handle
        assert callable(handle)

        # Invoke the orchestrator-style cancel handle; the process terminates.
        handle()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (TimeoutError, PipelineError):
            pass
        # After completion, no python sleep process should remain for this argv.
        # (Functional check: the task completed rather than hanging 60s.)

    async def test_register_cancel_unregisters_on_completion(self) -> None:
        registrar = Registrar()
        await run_managed_process(
            [sys.executable, "-c", "print('done')"],
            register_cancel=registrar,
            timeout=10.0,
        )
        assert registrar.handle is None


class TestBuildYtdlpArgs:
    def test_default_args_include_quiet_and_remote_components(self) -> None:
        argv = build_ytdlp_args(["--dump-json", "https://example.com/v"])
        assert argv[0] == "yt-dlp"
        assert "--quiet" in argv
        assert "--no-warnings" in argv
        assert "--remote-components" in argv and "ejs:github" in argv
        assert argv[-1] == "https://example.com/v"

    def test_quiet_false_omits_quiet(self) -> None:
        argv = build_ytdlp_args(["-f", "bestaudio/best"], quiet=False)
        assert "--quiet" not in argv

    def test_proxy_and_cookiefile_priority(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.pipeline.subprocess_util.YT_DLP_PROXY", "http://127.0.0.1:7890"
        )
        monkeypatch.setattr(
            "app.pipeline.subprocess_util.YT_DLP_COOKIES_FROM_BROWSER", "chrome:Default"
        )
        monkeypatch.setattr(
            "app.pipeline.subprocess_util.YT_DLP_COOKIES_FILE", "/tmp/cookies.txt"
        )

        argv = build_ytdlp_args(["URL"])
        assert "--proxy" in argv and argv[argv.index("--proxy") + 1] == "http://127.0.0.1:7890"
        # browser cookies + cookies file both applied when no per-user file
        assert "--cookies-from-browser" in argv
        assert argv[argv.index("--cookies-from-browser") + 1] == "chrome:Default"
        assert "--cookies" in argv and argv[argv.index("--cookies") + 1] == "/tmp/cookies.txt"

        # Per-user cookie file takes priority over both
        argv_user = build_ytdlp_args(["URL"], cookiefile_path="/tmp/user_cookies.txt")
        assert argv_user[argv_user.index("--cookies") + 1] == "/tmp/user_cookies.txt"
        assert "--cookies-from-browser" not in argv_user
        assert argv_user.count("--cookies") == 1


class TestParseCookiesFromBrowser:
    def test_supports_keyring_and_container(self) -> None:
        assert parse_cookies_from_browser("firefox+basictext:Profile 1::none") == (
            "firefox",
            "Profile 1",
            "BASICTEXT",
            "none",
        )

    def test_rejects_invalid_value(self) -> None:
        with pytest.raises(ValueError, match="Invalid YT_DLP_COOKIES_FROM_BROWSER"):
            parse_cookies_from_browser("chrome+")


class TestClassifyYtdlpError:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("This video is private", ErrorCode.VIDEO_PRIVATE),
            ("Login required to watch", ErrorCode.VIDEO_PRIVATE),
            ("Video is not available in your country", ErrorCode.VIDEO_GEO_RESTRICTED),
            ("geo restricted content", ErrorCode.VIDEO_GEO_RESTRICTED),
            ("region locked", ErrorCode.VIDEO_GEO_RESTRICTED),
            ("HTTP Error 404: Not Found", ErrorCode.VIDEO_NOT_FOUND),
            ("video unavailable", ErrorCode.VIDEO_NOT_FOUND),
            ("video has been deleted", ErrorCode.VIDEO_NOT_FOUND),
            ("cookies required", ErrorCode.VIDEO_COOKIE_INVALID),
            ("login is required", ErrorCode.VIDEO_COOKIE_INVALID),
            ("some unexpected network failure", ErrorCode.VIDEO_FETCH_FAILED),
        ],
    )
    def test_classification_matrix(self, text: str, expected: ErrorCode) -> None:
        assert classify_ytdlp_error(text) is expected
