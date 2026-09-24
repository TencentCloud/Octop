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

export type ShellStatusLevel = "progress" | "error";

/** Copy key (see the Go shell's status_codes.go) plus its interpolation args. */
export type DesktopStatus = {
  code: string;
  level: ShellStatusLevel;
  args: Record<string, unknown>;
};

/** Reads the `{ code, level, args }` payload the shell sends. */
export function statusFromEvent(ev: unknown): DesktopStatus {
  const raw =
    ev && typeof ev === "object"
      ? (ev as { data?: unknown; payload?: unknown }).data ??
        (ev as { payload?: unknown }).payload ??
        ev
      : ev;
  if (raw && typeof raw === "object") {
    const payload = raw as {
      code?: unknown;
      level?: unknown;
      args?: unknown;
    };
    if (typeof payload.code === "string") {
      return {
        code: payload.code,
        level: payload.level === "error" ? "error" : "progress",
        args:
          payload.args && typeof payload.args === "object"
            ? (payload.args as Record<string, unknown>)
            : {},
      };
    }
  }
  return { code: "", level: "progress", args: {} };
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
