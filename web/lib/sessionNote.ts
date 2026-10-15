"use client";

// The one calm note shown after the app restarts a visitor's demo session on its own (components/
// SandboxBanner.tsx), and the rule that it never shares the screen with the "Waking the demo" notice.
// A module store read with useSyncExternalStore, so the note and the notice see the same state at once.
import { useSyncExternalStore } from "react";

/** How long the note stays. It is information, not a task: nothing is waiting on the visitor. */
export const RESTART_NOTE_MS = 8000;

let noteOn = false;
let wakingNotices = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function showRestartNote() {
  noteOn = true;
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    noteOn = false;
    emit();
  }, RESTART_NOTE_MS);
  emit();
}

/** A Waking notice is on screen until the returned function is called. While one is, the restart note stays out of the way. */
export function registerWakingNotice(): () => void {
  wakingNotices += 1;
  emit();
  return () => {
    wakingNotices -= 1;
    emit();
  };
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function useRestartNote(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => noteOn && wakingNotices === 0,
    () => false,
  );
}
