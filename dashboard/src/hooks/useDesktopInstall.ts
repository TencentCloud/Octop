import { useSyncExternalStore } from "react";

import { desktopApi } from "../api/modules/desktop";

export type DesktopInstallPhase =
  | "idle"
  | "installing"
  | "install_success"
  | "install_failed";

export interface DesktopInstallState {
  phase: DesktopInstallPhase;
  logs: string[];
}

// Module-level store so the install progress (and its SSE stream) persists
// across RemoteDesktopPage mount/unmount. Leaving and re-entering the page
// keeps showing the ongoing installation instead of aborting it.
let state: DesktopInstallState = { phase: "idle", logs: [] };
let controller: AbortController | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) {
    listener();
  }
}

function setState(next: DesktopInstallState): void {
  state = next;
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): DesktopInstallState {
  return state;
}

export function startDesktopInstall(): void {
  if (state.phase === "installing") return;
  controller?.abort();
  setState({ phase: "installing", logs: [] });
  controller = desktopApi.installDesktop(
    (line) => setState({ ...state, logs: [...state.logs, line] }),
    (success) => {
      controller = null;
      setState({
        ...state,
        phase: success ? "install_success" : "install_failed",
      });
    },
  );
}

export function cancelDesktopInstall(): void {
  controller?.abort();
  controller = null;
  setState({ phase: "idle", logs: [] });
}

export function resetDesktopInstall(): void {
  if (state.phase === "installing") return;
  setState({ phase: "idle", logs: [] });
}

export function useDesktopInstall(): DesktopInstallState {
  return useSyncExternalStore(subscribe, getSnapshot);
}
