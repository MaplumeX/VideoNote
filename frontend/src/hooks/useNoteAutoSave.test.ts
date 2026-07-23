import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useNoteAutoSave } from "./useNoteAutoSave";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, reject, resolve };
}

describe("useNoteAutoSave", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("saves the first single-character edit after the debounce", async () => {
    const save = vi.fn(async (snapshot: string) => snapshot);
    const { result } = renderHook(() => useNoteAutoSave({ save }));

    act(() => {
      result.current.reset("initial");
      result.current.handleChange("initial!");
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1499);
    });
    expect(save).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("initial!");
    expect(result.current.lastSavedMarkdown).toBe("initial!");
  });

  it("serializes requests and immediately catches up edits made during a save", async () => {
    const firstSave = deferred<string>();
    const secondSave = deferred<string>();
    const save = vi
      .fn<(snapshot: string) => Promise<string>>()
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise);
    const onSaved = vi.fn();
    const { result } = renderHook(() => useNoteAutoSave({ save, onSaved }));

    act(() => {
      result.current.reset("initial");
      result.current.handleChange("version one");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    act(() => {
      result.current.handleChange("version two");
    });
    expect(save).toHaveBeenCalledTimes(1);

    await act(async () => {
      firstSave.resolve("first response");
      await firstSave.promise;
    });

    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenNthCalledWith(1, "version one");
    expect(save).toHaveBeenNthCalledWith(2, "version two");
    expect(result.current.lastSavedMarkdown).toBe("version one");
    expect(result.current.saving).toBe(true);

    await act(async () => {
      secondSave.resolve("second response");
      await secondSave.promise;
    });

    expect(result.current.lastSavedMarkdown).toBe("version two");
    expect(result.current.saving).toBe(false);
    expect(onSaved).toHaveBeenNthCalledWith(1, "first response", "version one");
    expect(onSaved).toHaveBeenNthCalledWith(2, "second response", "version two");
  });

  it("keeps failed content dirty and retries it on an explicit save", async () => {
    const save = vi
      .fn<(snapshot: string) => Promise<string>>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("saved");
    const { result } = renderHook(() => useNoteAutoSave({ save }));

    act(() => {
      result.current.reset("initial");
      result.current.handleChange("draft");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    expect(result.current.saveError).toBe(true);
    expect(result.current.lastSavedMarkdown).toBe("initial");

    await act(async () => {
      await result.current.saveNow();
    });

    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith("draft");
    expect(result.current.saveError).toBe(false);
    expect(result.current.lastSavedMarkdown).toBe("draft");
  });

  it.each([
    { ctrlKey: true, metaKey: false },
    { ctrlKey: false, metaKey: true },
  ])("saves immediately on Cmd/Ctrl+S and cancels the pending debounce", async (modifiers) => {
    const save = vi.fn(async (snapshot: string) => snapshot);
    const { result } = renderHook(() => useNoteAutoSave({ save }));

    act(() => {
      result.current.reset("initial");
      result.current.handleChange("manual");
    });
    const shortcut = new KeyboardEvent("keydown", {
      ...modifiers,
      cancelable: true,
      key: "s",
    });
    await act(async () => {
      window.dispatchEvent(shortcut);
      await Promise.resolve();
    });

    expect(shortcut.defaultPrevented).toBe(true);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("manual");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("ignores an obsolete response after switching notes", async () => {
    const oldSave = deferred<string>();
    const onSaved = vi.fn();
    const save = vi.fn(() => oldSave.promise);
    const { result } = renderHook(() => useNoteAutoSave({ save, onSaved }));

    act(() => {
      result.current.reset("old");
      result.current.handleChange("old draft");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    act(() => {
      result.current.reset("new note");
    });
    await act(async () => {
      oldSave.resolve("obsolete response");
      await oldSave.promise;
    });

    expect(onSaved).not.toHaveBeenCalled();
    expect(result.current.lastSavedMarkdown).toBe("new note");
    expect(result.current.saving).toBe(false);
  });
});
