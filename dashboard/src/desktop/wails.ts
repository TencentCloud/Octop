export type DesktopSettings = {
  locale: string;
  autostart: boolean;
  minimizeToTray: boolean;
  preventSleep: boolean;
  port?: number;
};

type WailsRuntime = {
  Call: {
    ByName: (name: string, ...args: unknown[]) => Promise<unknown>;
  };
  Events: {
    On: (name: string, cb: (ev: unknown) => void) => void;
  };
};

let runtimePromise: Promise<WailsRuntime | null> | null = null;

export function loadWailsRuntime(): Promise<WailsRuntime | null> {
  if (!runtimePromise) {
    const spec = "/wails/runtime.js";
    runtimePromise = import(/* @vite-ignore */ spec)
      .then((mod) => mod as WailsRuntime)
      .catch(() => null);
  }
  return runtimePromise;
}

export async function callApp<T>(name: string, ...args: unknown[]): Promise<T> {
  const rt = await loadWailsRuntime();
  if (!rt) {
    throw new Error("Wails runtime is not available");
  }
  return rt.Call.ByName("main.App." + name, ...args) as Promise<T>;
}

export type DesktopStatus = { text: string; error: boolean };

/** Reads the desktop:status payload: `{ message, error }` in the event data. */
export function statusFromEvent(ev: unknown): DesktopStatus {
  if (typeof ev === "string") return { text: ev, error: false };
  if (ev && typeof ev === "object") {
    const rec = ev as { data?: unknown; payload?: unknown };
    const raw = rec.data ?? rec.payload ?? ev;
    if (typeof raw === "string") return { text: raw, error: false };
    if (raw && typeof raw === "object") {
      const payload = raw as { message?: unknown; error?: unknown };
      if (typeof payload.message === "string") {
        return { text: payload.message, error: payload.error === true };
      }
    }
  }
  return { text: String(ev), error: false };
}

export function isStuckStatus(text: string): boolean {
  return /未就绪|did not become ready|无法连接|Could not connect/.test(text);
}

export async function onDesktopStatus(
  callback: (status: DesktopStatus) => void,
): Promise<void> {
  const rt = await loadWailsRuntime();
  if (!rt) return;
  rt.Events.On("desktop:status", (ev: unknown) => {
    callback(statusFromEvent(ev));
  });
}
