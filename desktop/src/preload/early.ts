import { contextBridge, ipcRenderer } from "electron";
import { EARLY_IPC } from "../shared/early-ipc";

/**
 * Bridge for the shell's own pages (splash, fatal error result).
 *
 * The Dashboard gets ``preload/index.ts``; these two static documents get this
 * one instead. A failed launch has exactly one thing it can usefully ask for —
 * "start over" — so that is the entire surface. Nothing here reads files, opens
 * windows, or reaches the network.
 */
export interface EarlyShellBridge {
  /** Quit and relaunch the app, i.e. run boot again from the top. */
  restart(): void;
}

const bridge: EarlyShellBridge = {
  restart(): void {
    ipcRenderer.send(EARLY_IPC.restart);
  },
};

contextBridge.exposeInMainWorld("octopShell", bridge);
