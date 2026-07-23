import { useCallback, useEffect, useRef, useState } from "react";

interface UseNoteAutoSaveOptions<TResult> {
  delay?: number;
  onSaved?: (result: TResult, snapshot: string) => void;
  save: (snapshot: string) => Promise<TResult>;
}

interface SaveRequest {
  generation: number;
  snapshot: string;
}

export function useNoteAutoSave<TResult>({
  delay = 1500,
  onSaved,
  save,
}: UseNoteAutoSaveOptions<TResult>) {
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [lastSavedMarkdown, setLastSavedMarkdown] = useState("");

  const latestMarkdownRef = useRef("");
  const lastSavedMarkdownRef = useRef("");
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const activeRequestRef = useRef<SaveRequest | null>(null);
  const saveQueuedRef = useRef(false);
  const generationRef = useRef(0);
  const mountedRef = useRef(true);
  const saveRef = useRef(save);
  const onSavedRef = useRef(onSaved);

  saveRef.current = save;
  onSavedRef.current = onSaved;

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = undefined;
    }
  }, []);

  const saveLatest = useCallback(async () => {
    clearTimer();

    const activeRequest = activeRequestRef.current;
    if (activeRequest) {
      if (latestMarkdownRef.current !== activeRequest.snapshot) {
        saveQueuedRef.current = true;
      }
      return;
    }

    const snapshot = latestMarkdownRef.current;
    if (snapshot === lastSavedMarkdownRef.current) return;

    const request: SaveRequest = {
      generation: generationRef.current,
      snapshot,
    };
    activeRequestRef.current = request;
    saveQueuedRef.current = false;
    setSaving(true);
    setSaveError(false);

    let succeeded = false;
    try {
      const result = await saveRef.current(snapshot);
      if (
        !mountedRef.current
        || request.generation !== generationRef.current
        || activeRequestRef.current !== request
      ) {
        return;
      }

      succeeded = true;
      lastSavedMarkdownRef.current = snapshot;
      setLastSavedMarkdown(snapshot);
      onSavedRef.current?.(result, snapshot);
    } catch {
      if (
        mountedRef.current
        && request.generation === generationRef.current
        && activeRequestRef.current === request
      ) {
        setSaveError(true);
      }
    } finally {
      if (
        mountedRef.current
        && request.generation === generationRef.current
        && activeRequestRef.current === request
      ) {
        const queuedWhileSaving = saveQueuedRef.current;
        activeRequestRef.current = null;
        saveQueuedRef.current = false;
        setSaving(false);

        const remainsDirty = latestMarkdownRef.current !== lastSavedMarkdownRef.current;
        if (remainsDirty && (succeeded || queuedWhileSaving)) {
          void saveLatest();
        }
      }
    }
  }, [clearTimer]);

  const handleChange = useCallback((markdown: string) => {
    latestMarkdownRef.current = markdown;
    setSaveError(false);

    const activeRequest = activeRequestRef.current;
    if (activeRequest && markdown !== activeRequest.snapshot) {
      saveQueuedRef.current = true;
    }

    clearTimer();
    timerRef.current = setTimeout(() => {
      timerRef.current = undefined;
      void saveLatest();
    }, delay);
  }, [clearTimer, delay, saveLatest]);

  const reset = useCallback((markdown: string) => {
    clearTimer();
    generationRef.current += 1;
    activeRequestRef.current = null;
    saveQueuedRef.current = false;
    latestMarkdownRef.current = markdown;
    lastSavedMarkdownRef.current = markdown;
    setLastSavedMarkdown(markdown);
    setSaving(false);
    setSaveError(false);
  }, [clearTimer]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const isSaveShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s";
      const hasUnsavedChanges = latestMarkdownRef.current !== lastSavedMarkdownRef.current;
      if (!isSaveShortcut || !hasUnsavedChanges) return;

      event.preventDefault();
      void saveLatest();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [saveLatest]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      activeRequestRef.current = null;
      clearTimer();
    };
  }, [clearTimer]);

  return {
    handleChange,
    lastSavedMarkdown,
    reset,
    saveError,
    saveNow: saveLatest,
    saving,
  };
}
