"""State-machine-driven pipeline orchestrator (C4).

Responsibilities (single owner of DB writes for task state):

- run one ``ExecutionPlan`` phase by phase per the state machine, persisting
  artifacts and checkpoints after each successful phase;
- write terminal states (failed / cancelled / complete) with conditional,
  idempotent guarded updates — cancellation always wins races;
- manage cancel handles: DB-persisted intent (``request_task_cancel``) plus
  the in-memory registry so the current stage's subprocess dies immediately;
- clean up per-job temp files (WAV, per-user cookie temp file, uploads) at
  the ``complete``/``cancelled`` terminal states — ``failed`` deliberately
  retains them for checkpoint-resumed retries (delayed housekeeping cleans up);
- restart recovery (``recover``) and checkpoint-resumed user retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app import config, db
from app.pipeline.context import (
    STAGES,
    CancelHandleRegistry,
    ExecutionPlan,
    advance,
    build_stage_context,
    checkpoint_artifacts,
    detect_video_platform,
    normalize_language,
    parse_checkpoint,
    path_for_source,
    resolve_providers,
    wav_path_for,
)
from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.state import (
    ArtifactKind,
    Checkpoint,
    PipelinePhase,
    TaskStatus,
    resume_point,
)

logger = logging.getLogger(__name__)

class Orchestrator:
    """Executes pipeline tasks; the sole writer of task state in the new chain."""

    def __init__(self) -> None:
        self._registries: dict[str, CancelHandleRegistry] = {}
        # Test seam: injectable stage registry (fake stages, zero network).
        self.stages: dict[PipelinePhase, object] = dict(STAGES)

    # --- execution -----------------------------------------------------

    async def run(self, plan: ExecutionPlan) -> None:
        """Run one task to a terminal state (or a checkpointed interruption)."""
        job_id = plan.job_id
        registry = CancelHandleRegistry()
        self._registries[job_id] = registry
        cookiefile: str | None = None
        extra: dict[str, object] = {}
        if plan.source_type == "url" and plan.url:
            extra["url"] = plan.url
            # Per-user cookie temp file, shared by every yt-dlp stage of the
            # run (fetch/subtitle/audio — legacy semantics). Cleaned in the
            # finally block below.
            cookiefile = await self._write_cookiefile(job_id, plan.url)
            if cookiefile:
                extra["cookiefile"] = cookiefile
        if plan.source_type == "upload" and plan.input_path:
            extra["input_path"] = plan.input_path

        try:
            row = await db.read_checkpoint(job_id)
            checkpoint = parse_checkpoint(row)
            checkpoint = await self._enrich_checkpoint(job_id, checkpoint)
            was_resumed = checkpoint is not None
            phase = resume_point(plan.path, checkpoint)
            artifacts = checkpoint_artifacts(plan, checkpoint)
            if was_resumed and phase in (
                PipelinePhase.transcribe,
                # audio itself still re-runs and re-derives the WAV; only a
                # resume *past* audio depends on the persisted WAV.
            ) and not await self._restore_audio_path(job_id, extra, plan):
                # audio_path is a non-artifact extra that is not persisted by
                # the checkpoint; the per-job WAV (C2 contract) restores it so
                # a resumed transcribe phase has its input back. When the WAV
                # is gone, rewind only to the audio phase: the checkpoint's
                # artifacts and resume flag stay, so fetch/subtitle (and any
                # other artifact-backed phase) keep their resume short-circuit
                # and are not re-executed.
                phase = PipelinePhase.audio

            while phase is not None:
                # Durable cancel intent persisted while we were between phases.
                if row is not None and (row.get("cancel_requested") or 0):
                    await self._finalize_cancelled(job_id)
                    return

                ok = await db.update_task_status(
                    job_id,
                    TaskStatus.running.value,
                    phase=phase.value,
                    phase_progress=0.0,
                    message=f"Running {phase.value}",
                )
                if not ok:
                    # Cancellation or terminal state won the race.
                    await self._maybe_cancelled(job_id)
                    return

                stage = self.stages[phase]
                ctx = build_stage_context(plan, registry, extra)
                try:
                    result = await stage.run(ctx, resume=was_resumed)
                except asyncio.CancelledError:
                    # Distinguish user cancellation (durable intent persisted)
                    # from a shutdown cancel (task.cancel() from
                    # PipelineTaskRunner.shutdown): the former writes the
                    # cancelled terminal state; the latter leaves the row
                    # recoverable so restart recovery resumes it (durable-jobs
                    # contract: shutdown preserves recoverable state).
                    row = await db.read_checkpoint(job_id)
                    if row is not None and (row.get("cancel_requested") or 0):
                        await self._finalize_cancelled(job_id)
                    else:
                        logger.info(
                            "Task %s interrupted by shutdown; left recoverable",
                            job_id,
                        )
                    raise
                except PipelineError as e:
                    logger.warning(
                        "Task %s failed in %s: %s", job_id, phase, e
                    )
                    await self._finalize_failed(job_id, e.code, e.detail)
                    return
                except Exception as e:
                    logger.exception("Task %s unexpected failure in %s", job_id, phase)
                    pe = PipelineError(ErrorCode.PROCESSING_FAILED, detail=str(e), cause=e)
                    await self._finalize_failed(job_id, pe.code, pe.detail)
                    return

                # Persist artifacts, then checkpoint the phase (conditional:
                # a persisted cancellation wins and drops the write).
                for kind, content in result.outputs.items():
                    await db.save_artifact(job_id, kind.value, content)
                    artifacts = artifacts | {kind}
                    if kind is ArtifactKind.video_meta and isinstance(content, dict):
                        # Surface title/thumbnail on the task row immediately
                        # (legacy update_task_meta semantics) so the UI shows
                        # them while the pipeline is still running — the
                        # complete-time write alone leaves them NULL for the
                        # whole run.
                        await db.update_task_meta(
                            job_id,
                            content.get("title") or None,
                            content.get("thumbnail") or None,
                        )
                saved = await db.save_checkpoint(
                    job_id,
                    phase.value,
                    status=TaskStatus.running.value,
                    phase=phase.value,
                )
                if not saved:
                    await self._maybe_cancelled(job_id)
                    return

                # Cross-stage extras (audio_path for transcribe, notes for the
                # terminal write) merge into the task-level extra dict.
                extra.update(result.extra)
                phase = advance(plan.path, phase, artifact_kinds=artifacts)
                was_resumed = False

            await self._finalize_complete(job_id, extra)
        finally:
            self._registries.pop(job_id, None)
            if cookiefile:
                Path(cookiefile).unlink(missing_ok=True)

    async def _write_cookiefile(self, job_id: str, url: str) -> str | None:
        """Materialize the user's per-platform cookie file for URL stages."""
        from app.pipeline.context import write_user_cookiefile

        task = await db.get_task(job_id)
        return await write_user_cookiefile(task.get("user_id") if task else None, url)

    async def _enrich_checkpoint(
        self, job_id: str, checkpoint: Checkpoint | None
    ) -> Checkpoint | None:
        """Attach durably persisted artifact kinds to the parsed checkpoint.

        The persisted checkpoint row carries only ``completed_phase``; the
        subtitle-hit resume rule (skip audio + transcribe, resume at notegen)
        is expressed by artifact presence, so the subtitle artifact is read
        from the store here. Without this, a subtitle-hit run resumed from
        its checkpoint would needlessly re-run audio + transcribe.
        """
        if checkpoint is None:
            return None
        subtitle = await db.get_artifact(job_id, ArtifactKind.subtitle.value)
        if isinstance(subtitle, str) and subtitle:
            return Checkpoint(
                completed_phase=checkpoint.completed_phase,
                artifacts=frozenset({ArtifactKind.subtitle}),
            )
        return checkpoint

    async def _restore_audio_path(
        self, job_id: str, extra: dict[str, object], plan: ExecutionPlan
    ) -> bool:
        """Re-derive the audio WAV path for a resumed run past the audio phase.

        The audio stage persists the per-job WAV to
        ``tmp/videonote_pipeline_audio/{job_id}.wav`` (C2 contract); on a
        checkpoint resume past the audio phase the file is normally still
        there, so the transcribe stage's input can be restored without
        re-running audio. Returns True when the resume can proceed past the
        audio phase. When the WAV is gone (temp dir cleaned), the audio phase
        must re-run: the caller rewinds only the phase pointer to audio,
        keeping the checkpoint's artifacts so earlier artifact-backed phases
        (fetch/subtitle) stay skipped.
        """
        wav = wav_path_for(job_id)
        if wav.is_file():
            extra["audio_path"] = str(wav)
            return True
        logger.info(
            "WAV for %s missing at resume; audio phase will re-run", job_id
        )
        return False

    # --- terminal states -------------------------------------------------

    async def _finalize_complete(self, job_id: str, extra: dict[str, object]) -> None:
        notes = extra.get("notes")
        if not isinstance(notes, str) or not notes:
            # The transition table guarantees notegen ran; a missing notes
            # extra is a defensive failure, not a silent success.
            await self._finalize_failed(
                job_id, ErrorCode.PROCESSING_FAILED, "notes missing at completion"
            )
            return

        meta = await db.get_artifact(job_id, ArtifactKind.video_meta.value)
        title: str | None = None
        thumbnail: str | None = None
        if isinstance(meta, dict):
            t = meta.get("title")
            title = t if isinstance(t, str) and t else None
            th = meta.get("thumbnail")
            thumbnail = th if isinstance(th, str) and th else None

        result_json = json.dumps({"markdown": notes, "title": title})
        await db.set_task_terminal(
            job_id,
            TaskStatus.complete.value,
            message="Done",
            result_json=result_json,
            title=title,
            thumbnail_url=thumbnail,
        )
        await self._cleanup_files(job_id)

    async def _finalize_failed(
        self, job_id: str, code: ErrorCode, detail: str
    ) -> None:
        message = f"{code.value}: {detail}" if detail else code.value
        await db.set_task_terminal(
            job_id,
            TaskStatus.failed.value,
            message=message,
            last_error_code=code.value,
        )
        # Files are deliberately NOT cleaned up on failure: the per-job WAV
        # and the upload input are kept so a retry resumes from the
        # checkpoint instead of restarting the whole pipeline. The delayed
        # housekeeping (db.cleanup_failed_task_files, 7 days) is the safety
        # net that eventually removes them.


    async def _finalize_cancelled(self, job_id: str) -> None:
        await db.set_task_terminal(
            job_id,
            TaskStatus.cancelled.value,
            message="Cancelled",
            last_error_code=ErrorCode.TASK_CANCELLED.value,
        )
        await self._cleanup_files(job_id)

    async def _maybe_cancelled(self, job_id: str) -> None:
        """After a guarded write lost its race, converge to cancelled if intent exists."""
        task = await db.get_task(job_id)
        if task is None:
            return
        if task.get("cancel_requested") or task.get("status") == TaskStatus.cancelled.value:
            await db.set_task_terminal(
                job_id,
                TaskStatus.cancelled.value,
                message="Cancelled",
                last_error_code=ErrorCode.TASK_CANCELLED.value,
            )
        await self._cleanup_files(job_id)

    # --- cleanup -----------------------------------------------------------

    async def _cleanup_files(self, job_id: str) -> None:
        """Remove per-job temp files at a terminal state (upload input, WAV)."""
        wav_path_for(job_id).unlink(missing_ok=True)
        task = await db.get_task(job_id)
        if task is None:
            return
        input_path = _safe_upload_path(task.get("input_file_path"))
        if input_path is not None and input_path.is_file():
            input_path.unlink(missing_ok=True)
            await db.clear_task_input_file(job_id)

    # --- cancellation -------------------------------------------------------

    def cancel(self, job_id: str) -> bool:
        """Trigger the current stage's cancel handle (subprocess kill).

        The asyncio task cancel is issued by the caller (the runner); this
        method only fires the stage-level handle so in-flight subprocesses die
        immediately. Returns True when a registry existed.
        """
        registry = self._registries.get(job_id)
        if registry is None:
            return False
        registry.trigger()
        return True

    # --- scheduling entry points ---------------------------------------------

    async def schedule_task(self, job_id: str, *, bump_attempt: bool = True) -> bool:
        """Build the execution plan from the task row and schedule a run.

        Returns False when the task is missing, not schedulable, or already
        running. ``bump_attempt`` increments the durable attempt counter as
        part of scheduling (durable-jobs contract: one increment per dispatch).
        """
        from app.pipeline.runner import pipeline_runner

        if bump_attempt and not await db.increment_attempt(job_id):
            return False
        task = await db.get_task(job_id)
        if task is None:
            return False
        provider = await resolve_providers(task.get("user_id"))
        plan = ExecutionPlan(
            job_id=job_id,
            source_type=task.get("source_type") or "url",
            language=normalize_language(task.get("language")),
            provider=provider,
            path=path_for_source(task.get("source_type")),
            url=task.get("video_url"),
            input_path=_safe_upload_path(task.get("input_file_path")),
        )
        return pipeline_runner.schedule(job_id, lambda: self.run(plan))

    # --- restart recovery ------------------------------------------------

    async def recover(self) -> None:
        """Reschedule durable non-terminal tasks after application startup."""
        for task in await db.get_recoverable_tasks():
            job_id = task["job_id"]

            if task.get("attempt_count", 0) >= db.MAX_TASK_ATTEMPTS:
                await db.set_task_terminal(
                    job_id,
                    TaskStatus.failed.value,
                    message=ErrorCode.TASK_RECOVERY_MAX_ATTEMPTS.value,
                    last_error_code=ErrorCode.TASK_RECOVERY_MAX_ATTEMPTS.value,
                )
                continue

            source_type = task.get("source_type")
            if source_type == "url" and task.get("video_url"):
                if detect_video_platform(task["video_url"]) == "unknown":
                    await db.set_task_terminal(
                        job_id,
                        TaskStatus.failed.value,
                        message=ErrorCode.TASK_RECOVERY_UNSUPPORTED_URL.value,
                        last_error_code=(
                            ErrorCode.TASK_RECOVERY_UNSUPPORTED_URL.value
                        ),
                    )
                    continue
                await self.schedule_task(job_id)
                continue

            if source_type == "upload":
                file_path = _safe_upload_path(task.get("input_file_path"))
                if file_path is not None and file_path.is_file():
                    await self.schedule_task(job_id)
                    continue

            await db.set_task_terminal(
                job_id,
                TaskStatus.failed.value,
                message=ErrorCode.TASK_RECOVERY_INPUT_INVALID.value,
                last_error_code=ErrorCode.TASK_RECOVERY_INPUT_INVALID.value,
            )

    # --- user retry --------------------------------------------------------

    async def retry(self, job_id: str) -> bool:
        """Retry a failed/cancelled task from its persisted checkpoint.

        Only failed/cancelled tasks may be retried (409 semantics live in the
        route layer). Resets the persisted cancellation intent, bumps the
        attempt counter, and schedules a checkpoint-resumed run: completed
        phases with durable artifacts are not re-executed.
        """
        if not await db.reset_task_for_retry(job_id):
            return False
        return await self.schedule_task(job_id, bump_attempt=False)

def _safe_upload_path(path_value: str | None) -> Path | None:
    """Resolve a persisted upload path and reject paths outside UPLOAD_DIR.

    The upload root is resolved lazily from ``app.config`` so tests that
    rebind ``UPLOAD_DIR`` (monkeypatch) are honored.
    """
    if not path_value:
        return None
    path = Path(path_value).resolve()
    upload_root = Path(str(config.UPLOAD_DIR)).resolve()
    if path == upload_root or upload_root not in path.parents:
        return None
    return path

orchestrator = Orchestrator()
