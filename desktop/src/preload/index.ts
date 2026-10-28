import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";
import {
  IPC_CHANNELS,
  type ClientSettings,
  type IssuedSession,
  type PlatformInfo,
  type UpdateCheckResult,
  type WindowChromeTheme,
  type WsRelayEndpoint,
} from "../shared/ipc-contract";

/**
 * Minimal, typed bridge exposed to the sandboxed renderer as ``window.octopDesktop``.
 * No raw ipcRenderer, no file system, no shell execution, no arbitrary URLs.
 */

function subscribe<T>(channel: string, cb: (payload: T) => void): () => void {
  const listener = (_event: IpcRendererEvent, payload: T) => cb(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

/**
 * Read once and memoise: the relay binds before the window loads, so the value
 * cannot change during a launch, and URL builders call this from render paths
 * where awaiting is not an option.
 */
let wsEndpointCache: WsRelayEndpoint | null | undefined;

const bridge = {
  getPlatformInfo(): Promise<PlatformInfo> {
    return ipcRenderer.invoke(IPC_CHANNELS.getPlatformInfo);
  },
  openDirectoryPicker(): Promise<string | null> {
    return ipcRenderer.invoke(IPC_CHANNELS.openDirectoryPicker);
  },
  openFilePicker(): Promise<string | null> {
    return ipcRenderer.invoke(IPC_CHANNELS.openFilePicker);
  },
  onBackendReady(callback: (ready: { ok: boolean }) => void): () => void {
    return subscribe(IPC_CHANNELS.onBackendReady, callback);
  },
  /**
   * Report the page theme so the *native* window controls (traffic lights,
   * caption buttons) match it. Window buttons themselves are never driven from
   * here: minimise / maximise / close stay native.
   */
  setWindowChrome(theme: WindowChromeTheme): void {
    ipcRenderer.send(IPC_CHANNELS.windowChromeTheme, theme);
  },
  /**
   * Full screen hides the macOS traffic lights, so the page stops reserving
   * room for them. Fires only on change; the app never starts full screen.
   */
  onWindowFullscreenChange(callback: (fullscreen: boolean) => void): () => void {
    return subscribe(IPC_CHANNELS.windowChromeFullscreen, callback);
  },
  clientSettings: {
    get(): Promise<ClientSettings> {
      return ipcRenderer.invoke(IPC_CHANNELS.clientSettingsGet);
    },
    set(patch: Partial<ClientSettings>): Promise<ClientSettings> {
      return ipcRenderer.invoke(IPC_CHANNELS.clientSettingsSet, patch);
    },
  },
  /**
   * Where to dial WebSockets (§5.2). ``null`` when the shell has no relay, in
   * which case the Dashboard keeps deriving the address from the page origin.
   */
  wsEndpoint(): WsRelayEndpoint | null {
    if (wsEndpointCache === undefined) {
      wsEndpointCache = (ipcRenderer.sendSync(IPC_CHANNELS.wsEndpoint) as WsRelayEndpoint | null) ?? null;
    }
    return wsEndpointCache;
  },
  checkForUpdates(): Promise<UpdateCheckResult> {
    return ipcRenderer.invoke(IPC_CHANNELS.checkForUpdates);
  },
  openUpdateConfirmation(): Promise<void> {
    return ipcRenderer.invoke(IPC_CHANNELS.openUpdateConfirmation);
  },
  /**
   * Device session (§7 accounts). The renderer can ask for a JWT, but the
   * credential behind it never crosses this bridge.
   */
  session: {
    register(accessToken: string): Promise<boolean> {
      return ipcRenderer.invoke(IPC_CHANNELS.sessionRegister, accessToken);
    },
    renew(): Promise<IssuedSession | null> {
      return ipcRenderer.invoke(IPC_CHANNELS.sessionRenew);
    },
    revoke(accessToken: string): Promise<boolean> {
      return ipcRenderer.invoke(IPC_CHANNELS.sessionRevoke, accessToken);
    },
  },
} as const;

export type OctopDesktopBridge = typeof bridge;

contextBridge.exposeInMainWorld("octopDesktop", bridge);
