import { useEffect, useRef, useState } from "react";
import type { TaskStage, TaskProgress } from "../types";
import { getProgressUrl } from "../api/client";
import { authFetch } from "../auth/api";

export function useSSE(jobId: string | null) {
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const stageRef = useRef<TaskStage | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const abortController = new AbortController();
    abortRef.current = abortController;
    stageRef.current = null;

    const url = getProgressUrl(jobId);

    (async () => {
      try {
        const res = await authFetch(url, {
          signal: abortController.signal,
        });

        if (!res.ok || !res.body) {
          setError("Failed to connect to progress stream");
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          let currentEvent = "";
          let currentData = "";

          for (const line of lines) {
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              currentData = line.slice(5).trim();
            } else if (line === "" && currentData) {
              // End of event
              if (currentEvent === "progress") {
                const data: TaskProgress = JSON.parse(currentData);
                setProgress(data);
                stageRef.current = data.stage;
                if (data.stage === "failed") {
                  setError(data.message || "Processing failed");
                  return;
                }
                if (data.stage === "cancelled") {
                  setError("Task cancelled");
                  return;
                }
              } else if (currentEvent === "complete") {
                const data = JSON.parse(currentData);
                setResult(data.markdown);
                setError(null);
                return;
              }
              currentEvent = "";
              currentData = "";
            }
          }
        }
      } catch {
        if (abortController.signal.aborted) return;
        if (stageRef.current === "failed" || stageRef.current === "complete" || stageRef.current === "cancelled") return;
        setError("Connection to server lost");
      }
    })();

    return () => {
      abortController.abort();
      abortRef.current = null;
      stageRef.current = null;
    };
  }, [jobId]);

  return { progress, result, error };
}
