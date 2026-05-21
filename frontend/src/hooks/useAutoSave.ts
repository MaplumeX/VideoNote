import { useEffect, useRef, useState, useCallback } from "react";

interface UseAutoSaveOptions {
  jobId: string | null;
  editMarkdown: string;
  savedMarkdown: string;
  saveFn: (jobId: string, markdown: string) => Promise<unknown>;
  onSaveSuccess?: (result: unknown) => void;
  debounceMs?: number;
}

interface UseAutoSaveReturn {
  saving: boolean;
  saveError: string | null;
  hasUnsavedChanges: boolean;
  flush: () => Promise<void>;
}

export function useAutoSave({
  jobId,
  editMarkdown,
  savedMarkdown,
  saveFn,
  onSaveSuccess,
  debounceMs = 1500,
}: UseAutoSaveOptions): UseAutoSaveReturn {
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editMarkdownRef = useRef(editMarkdown);
  const jobIdRef = useRef(jobId);
  const savedMarkdownRef = useRef(savedMarkdown);
  const savingRef = useRef(false);
  const saveFnRef = useRef(saveFn);
  const onSaveSuccessRef = useRef(onSaveSuccess);
  // Guard: skip debounce after a jobId change until editMarkdown and
  // savedMarkdown align (i.e. the new note has been loaded).
  const jobIdChangeGuardRef = useRef(false);

  // Keep refs in sync with latest values
  editMarkdownRef.current = editMarkdown;
  jobIdRef.current = jobId;
  savedMarkdownRef.current = savedMarkdown;
  savingRef.current = saving;
  saveFnRef.current = saveFn;
  onSaveSuccessRef.current = onSaveSuccess;

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const performSave = useCallback(async () => {
    const currentJobId = jobIdRef.current;
    const currentMarkdown = editMarkdownRef.current;

    if (!currentJobId || savingRef.current) return;

    setSaving(true);
    setSaveError(null);

    try {
      const result = await saveFnRef.current(currentJobId, currentMarkdown);
      setHasUnsavedChanges(false);
      setSaving(false);
      onSaveSuccessRef.current?.(result);
      return result;
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
      setSaving(false);
      setHasUnsavedChanges(true);
    }
  }, []);

  const flush = useCallback(async () => {
    clearTimer();
    if (editMarkdownRef.current !== savedMarkdownRef.current) {
      await performSave();
    }
  }, [clearTimer, performSave]);

  // Detect unsaved changes and start debounce timer
  useEffect(() => {
    const dirty = editMarkdown !== savedMarkdown;

    // After a jobId change, skip debounce until editMarkdown and savedMarkdown
    // are aligned (new note loaded). Clear the guard once they match.
    if (jobIdChangeGuardRef.current) {
      if (dirty) {
        // New note not yet loaded — skip debounce
        return;
      }
      jobIdChangeGuardRef.current = false;
    }

    setHasUnsavedChanges(dirty);

    if (!dirty) {
      clearTimer();
      return;
    }

    // Cancel existing timer and start a new one
    clearTimer();
    timerRef.current = setTimeout(() => {
      performSave();
    }, debounceMs);

    return () => {
      clearTimer();
    };
  }, [editMarkdown, savedMarkdown, debounceMs, clearTimer, performSave]);

  // When jobId changes, flush pending changes for the old note before resetting
  useEffect(() => {
    return () => {
      // Cleanup runs when jobId is about to change.
      // At this point, refs still hold the OLD values.
      clearTimer();
      const oldJobId = jobIdRef.current;
      const oldMarkdown = editMarkdownRef.current;
      const oldSavedMarkdown = savedMarkdownRef.current;

      if (oldJobId && oldMarkdown !== oldSavedMarkdown) {
        // Fire-and-forget save — we cannot await in cleanup.
        // This ensures the old note's pending changes are persisted
        // before the new note loads.
        saveFnRef.current(oldJobId, oldMarkdown)
          .then((result) => {
            onSaveSuccessRef.current?.(result);
          })
          .catch(() => {
            // Best-effort flush on unmount; user will see error on next visit
          });
      }
    };
  }, [jobId, clearTimer]);

  // Reset state when jobId changes (note switch)
  useEffect(() => {
    jobIdChangeGuardRef.current = true;
    clearTimer();
    setSaveError(null);
    setSaving(false);
    setHasUnsavedChanges(false);
  }, [jobId, clearTimer]);

  // beforeunload handler
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (editMarkdownRef.current !== savedMarkdownRef.current) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, []);

  return { saving, saveError, hasUnsavedChanges, flush };
}
