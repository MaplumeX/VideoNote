"""Tests for pipeline error codes and centralized sanitization."""

from app.pipeline.errors import (
    MAX_DETAIL_LENGTH,
    ErrorCode,
    PipelineError,
    sanitize_detail,
)


class TestSanitizeDetail:
    def test_plain_text_passthrough(self) -> None:
        assert sanitize_detail("ffmpeg failed with code 1") == "ffmpeg failed with code 1"

    def test_strips_sk_api_keys(self) -> None:
        raw = "Request failed: sk-AbCdEf12345678GhIjKl rejected"
        assert sanitize_detail(raw) == "Request failed: [REDACTED] rejected"

    def test_strips_short_prefixed_keys_too(self) -> None:
        # sk- followed by >= 8 chars is redacted
        raw = "key sk-12345678 is invalid"
        assert "sk-12345678" not in sanitize_detail(raw)

    def test_strips_bearer_tokens(self) -> None:
        raw = "401 Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
        result = sanitize_detail(raw)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "Bearer" not in result

    def test_strips_lowercase_bearer(self) -> None:
        raw = "bearer abc123.def.ghi rejected"
        assert "abc123.def.ghi" not in sanitize_detail(raw)

    def test_strips_cookie_headers(self) -> None:
        raw = "HTTP error: Cookie: sessionid=supersecret; path=/\nmore"
        result = sanitize_detail(raw)
        assert "supersecret" not in result

    def test_strips_set_cookie_headers(self) -> None:
        raw = "Set-Cookie: token=abc; HttpOnly"
        assert "token=abc" not in sanitize_detail(raw)

    def test_truncates_to_200_chars(self) -> None:
        raw = "x" * 500
        assert len(sanitize_detail(raw)) == MAX_DETAIL_LENGTH

    def test_strips_whitespace(self) -> None:
        assert sanitize_detail("   \n something went wrong \t ") == "something went wrong"

    def test_empty_string(self) -> None:
        assert sanitize_detail("") == ""


class TestPipelineError:
    def test_detail_sanitized_at_construction(self) -> None:
        err = PipelineError(
            ErrorCode.TRANSCRIPTION_FAILED,
            detail="ASR rejected key sk-Zz9yX8w7V6u5T4s3",
        )
        assert "sk-Zz9yX8w7V6u5T4s3" not in err.detail
        assert "[REDACTED]" in err.detail

    def test_detail_truncated_at_construction(self) -> None:
        err = PipelineError(ErrorCode.PROCESSING_FAILED, detail="y" * 400)
        assert len(err.detail) == MAX_DETAIL_LENGTH

    def test_empty_detail(self) -> None:
        err = PipelineError(ErrorCode.VIDEO_NOT_FOUND)
        assert err.detail == ""
        assert str(err) == "VIDEO_NOT_FOUND"

    def test_str_includes_code_and_detail(self) -> None:
        err = PipelineError(ErrorCode.AUDIO_EXTRACTION_FAILED, detail="ffmpeg crashed")
        assert str(err) == "AUDIO_EXTRACTION_FAILED: ffmpeg crashed"

    def test_cause_is_chained(self) -> None:
        original = RuntimeError("boom")
        err = PipelineError(ErrorCode.PROCESSING_FAILED, cause=original)
        assert err.__cause__ is original

    def test_cause_text_not_leaked_into_detail(self) -> None:
        original = RuntimeError("secret sk-AbCdEf12345678Zz")
        err = PipelineError(ErrorCode.PROCESSING_FAILED, cause=original)
        assert err.detail == ""

    def test_error_code_enum_members(self) -> None:
        expected = {
            "VIDEO_PRIVATE", "VIDEO_GEO_RESTRICTED", "VIDEO_NOT_FOUND",
            "VIDEO_COOKIE_INVALID", "VIDEO_FETCH_FAILED",
            "SUBTITLE_EXTRACTION_FAILED", "AUDIO_EXTRACTION_FAILED",
            "TRANSCRIPTION_FAILED", "NOTE_GENERATION_FAILED",
            "PROCESSING_FAILED", "PROVIDER_NOT_CONFIGURED",
            "TASK_RECOVERY_MAX_ATTEMPTS", "TASK_RECOVERY_INPUT_INVALID",
            "TASK_RECOVERY_UNSUPPORTED_URL", "TASK_CANCELLED",
        }
        assert {code.value for code in ErrorCode} == expected
