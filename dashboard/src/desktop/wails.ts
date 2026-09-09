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

export function statusTextFromEvent(ev: unknown): string {
  if (typeof ev === "string") return ev;
  if (ev && typeof ev === "object") {
    const rec = ev as { data?: unknown; payload?: unknown };
    if (typeof rec.data === "string") return rec.data;
    if (typeof rec.payload === "string") return rec.payload;
  }
  return String(ev);
}

export function isStuckStatus(text: string): boolean {
  return /未就绪|did not become ready|无法连接|Could not connect/.test(text);
}

export async function onDesktopStatus(
  callback: (text: string) => void,
): Promise<void> {
  const rt = await loadWailsRuntime();
  if (!rt) return;
  rt.Events.On("desktop:status", (ev: unknown) => {
    callback(statusTextFromEvent(ev));
  });
}
