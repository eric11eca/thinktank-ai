import { useSyncExternalStore } from "react";

interface TurnUsage {
  input_tokens: number;
  output_tokens: number;
  startTime: number;
}

// Module-level store — survives React component remounts and tree changes.
let _turnUsage: TurnUsage | null = null;
let _turnUsageThreadId: string | null = null;
const _listeners = new Set<() => void>();

const STORAGE_PREFIX = "turn_usage:";

function getStorageKey(threadId: string) {
  return `${STORAGE_PREFIX}${threadId}`;
}

function readStoredUsage(threadId: string): TurnUsage | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(getStorageKey(threadId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TurnUsage;
    if (
      typeof parsed?.input_tokens !== "number" ||
      typeof parsed?.output_tokens !== "number" ||
      typeof parsed?.startTime !== "number"
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeStoredUsage(threadId: string, usage: TurnUsage | null) {
  if (typeof window === "undefined") return;
  try {
    if (!usage) {
      sessionStorage.removeItem(getStorageKey(threadId));
    } else {
      sessionStorage.setItem(getStorageKey(threadId), JSON.stringify(usage));
    }
  } catch {
    // Ignore storage errors (e.g. quota, disabled storage).
  }
}

function _emitChange() {
  for (const listener of _listeners) {
    listener();
  }
}

function _getSnapshot(): TurnUsage | null {
  return _turnUsage;
}

function _subscribe(listener: () => void): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

/** Bind turn usage to a thread and optionally restore from storage. */
export function setTurnUsageThread(
  threadId: string | null,
  options?: { restore?: boolean },
) {
  _turnUsageThreadId = threadId;
  if (!threadId || !options?.restore) return;
  const stored = readStoredUsage(threadId);
  if (stored) {
    _turnUsage = stored;
    _emitChange();
  }
}

/** Accumulate a token delta into the current turn. Sets startTime on the first call. */
export function updateTurnUsage(delta: {
  input_tokens: number;
  output_tokens: number;
}) {
  if (_turnUsage === null) {
    _turnUsage = {
      input_tokens: delta.input_tokens,
      output_tokens: delta.output_tokens,
      startTime: Date.now(),
    };
  } else {
    _turnUsage = {
      ..._turnUsage,
      input_tokens: _turnUsage.input_tokens + delta.input_tokens,
      output_tokens: _turnUsage.output_tokens + delta.output_tokens,
    };
  }
  if (_turnUsageThreadId && _turnUsage) {
    writeStoredUsage(_turnUsageThreadId, _turnUsage);
  }
  _emitChange();
}

/** Begin a new turn usage window with zeroed tokens. */
export function startTurnUsage() {
  _turnUsage = {
    input_tokens: 0,
    output_tokens: 0,
    startTime: Date.now(),
  };
  if (_turnUsageThreadId) {
    writeStoredUsage(_turnUsageThreadId, _turnUsage);
  }
  _emitChange();
}

/** Clear turn usage (call when starting a new turn or switching threads). */
export function resetTurnUsage() {
  _turnUsage = null;
  if (_turnUsageThreadId) {
    writeStoredUsage(_turnUsageThreadId, null);
  }
  _emitChange();
}

/** React hook — subscribes to turn usage changes. */
export function useTurnUsage(): TurnUsage | null {
  return useSyncExternalStore(_subscribe, _getSnapshot);
}
