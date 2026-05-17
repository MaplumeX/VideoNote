import { useEffect, useRef, useState } from "react";
import type { TaskStage, TaskProgress } from "../types";
import { getProgressUrl } from "../api/client";

export function useSSE(jobId: string | null) {
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const stageRef = useRef<TaskStage | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const url = getProgressUrl(jobId);
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("progress", (e) => {
      const data: TaskProgress = JSON.parse(e.data);
      setProgress(data);
      stageRef.current = data.stage;
      if (data.stage === "failed") {
        setError(data.message || "Processing failed");
        es.close();
      }
    });

    es.addEventListener("complete", (e) => {
      const data = JSON.parse(e.data);
      setResult(data.markdown);
      setError(null);
      es.close();
    });

    es.onerror = () => {
      if (stageRef.current === "failed" || stageRef.current === "complete") {
        // Already handled by progress/complete events
        return;
      }
      setError("Connection to server lost");
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
      stageRef.current = null;
    };
  }, [jobId]);

  return { progress, result, error };
}
