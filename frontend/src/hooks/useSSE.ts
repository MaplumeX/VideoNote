import { useEffect, useRef, useState } from "react";
import type { TaskPhase, TaskProgress } from "../types";
import {
  ApiError,
  fetchResult,
  fetchTaskById,
  getProgressUrl,
  translateTaskMessage,
} from "../api/client";
import { authFetch } from "../auth/api";
import { useTranslation } from "react-i18next";
import { createSSEParser } from "./sseParser";

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_DELAY_MS = 250;

function waitForReconnect(delayMs: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }

    const handleAbort = () => {
      window.clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", handleAbort);
      resolve();
    }, delayMs);
    signal.addEventListener("abort", handleAbort, { once: true });
  });
}

export function useSSE(jobId: string | null) {
  const { t } = useTranslation();
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Last phase observed while running — terminal SSE/REST payloads have
  // phase=null, but the UI needs it to localize which step failed.
  const lastPhaseRef = useRef<TaskPhase | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const abortController = new AbortController();
    abortRef.current = abortController;
    lastPhaseRef.current = null;
    setProgress(null);
    setResult(null);
    setError(null);

    const url = getProgressUrl(jobId);

    (async () => {
      let reconnectAttempt = 0;

      while (!abortController.signal.aborted) {
        let terminal = false;
        let firstEventReceived = false;
        try {
          const res = await authFetch(url, {
            signal: abortController.signal,
          });

          if (!res.ok || !res.body) {
            throw new Error(t("errors.sseConnectionFailed"));
          }

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          const parser = createSSEParser(({ event, data: rawData }) => {
            if (event === "progress") {
              const data: TaskProgress = JSON.parse(rawData);
              const translatedData = {
                ...data,
                message: translateTaskMessage(data.message),
              };
              setProgress(translatedData);
              if (data.phase) lastPhaseRef.current = data.phase;
              if (!firstEventReceived) {
                firstEventReceived = true;
                reconnectAttempt = 0;
              }
              if (data.status === "failed") {
                terminal = true;
                setError(
                  translatedData.message || t("errors.processingFailed"),
                );
              } else if (data.status === "cancelled") {
                terminal = true;
                setError(t("errors.taskCancelled"));
              }
            } else if (event === "complete") {
              const data: { markdown: string } = JSON.parse(rawData);
              terminal = true;
              lastPhaseRef.current = "notegen";
              if (!firstEventReceived) {
                firstEventReceived = true;
                reconnectAttempt = 0;
              }
              setResult(data.markdown);
              setError(null);
            }
          });

          while (!terminal) {
            const { done, value } = await reader.read();
            if (done) {
              parser.feed(decoder.decode());
              parser.end();
              break;
            }
            parser.feed(decoder.decode(value, { stream: true }));
          }
          if (terminal) return;
        } catch {
          if (abortController.signal.aborted) return;
        }

        try {
          const task = await fetchTaskById(jobId);
          if (abortController.signal.aborted) return;
          const recoveredProgress: TaskProgress = {
            status: task.status,
            phase: task.phase,
            phase_progress: task.phase_progress ?? 0,
            message: translateTaskMessage(task.message),
            attempt: 1,
            timestamp: new Date().toISOString(),
          };
          setProgress(recoveredProgress);
          if (task.phase) lastPhaseRef.current = task.phase;

          if (task.status === "complete") {
            try {
              const note = await fetchResult(jobId);
              if (abortController.signal.aborted) return;
              setResult(note.markdown);
              setError(null);
              return;
            } catch (e) {
              if (abortController.signal.aborted) return;
              // Deterministic errors (4xx) should not trigger reconnect loop.
              // Network errors and 5xx fall through to reconnect below.
              if (e instanceof ApiError && e.code !== "TASK_STILL_PROCESSING") {
                setError(e.message || t("errors.fetchResultFailed"));
                return;
              }
            }
          }
          if (task.status === "failed") {
            setError(
              recoveredProgress.message || t("errors.processingFailed"),
            );
            return;
          }
          if (task.status === "cancelled") {
            setError(t("errors.taskCancelled"));
            return;
          }
          // Task still processing — treat as successful recovery.
          // Reset reconnect counter and re-enter the loop to reconnect.
          reconnectAttempt = 0;
        } catch {
          if (abortController.signal.aborted) return;
        }

        // Only increment the reconnect counter if we never received an event
        // on this connection attempt (true network error / connection drop
        // before first event). If we did receive at least one event, the
        // server-side close was normal and we should reconnect without
        // consuming a retry slot.
        if (!firstEventReceived) {
          if (reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
            setError(t("errors.sseConnectionLost"));
            return;
          }
          const delay = RECONNECT_BASE_DELAY_MS * (2 ** reconnectAttempt);
          reconnectAttempt += 1;
          try {
            await waitForReconnect(delay, abortController.signal);
          } catch {
            return;
          }
        }
      }
    })();

    return () => {
      abortController.abort();
      abortRef.current = null;
      lastPhaseRef.current = null;
    };
  }, [jobId, t]);

  return { progress, result, error };
}
