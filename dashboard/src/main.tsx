// Must be the very first import so the beforeinstallprompt listener is
// registered synchronously before Chrome fires the event (which can happen
// before React mounts and useEffect runs).
import "./pwa-prompt";

import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { initI18n } from "./i18n";
import {
  clearChunkReloadFlag,
  installChunkLoadRecovery,
  isChunkLoadError,
  tryReloadOnStaleChunk,
} from "./utils/reloadOnStaleChunk";

if (typeof window !== "undefined") {
  // Recover from post-deploy stale hashed chunks (white screen → soft reload).
  installChunkLoadRecovery();

  const originalError = console.error;
  const originalWarn = console.warn;

  console.error = function (...args: unknown[]) {
    const msg = args[0]?.toString() || "";
    if (msg.includes(":first-child") || msg.includes("pseudo class")) {
      return;
    }
    originalError.apply(console, args);
  };

  console.warn = function (...args: unknown[]) {
    const msg = args[0]?.toString() || "";
    if (
      msg.includes(":first-child") ||
      msg.includes("pseudo class") ||
      msg.includes("potentially unsafe")
    ) {
      return;
    }
    originalWarn.apply(console, args);
  };

  // Catch unhandled Promise rejections (e.g. uncaught async errors)
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    // Chunk recovery (installChunkLoadRecovery) already handles these.
    if (isChunkLoadError(reason)) return;
    // Suppress common benign errors
    const msg = reason?.message || String(reason) || "";
    if (
      msg.includes("ResizeObserver") ||
      msg.includes("AbortError") ||
      msg.includes("The operation was aborted")
    ) {
      return;
    }
    console.error("[UnhandledRejection]", reason);
  });
}

void initI18n()
  .then(() => {
    clearChunkReloadFlag();
    createRoot(document.getElementById("root")!).render(<App />);
  })
  .catch((err: unknown) => {
    if (tryReloadOnStaleChunk(err)) return;
    console.error("[initI18n]", err);
  });

// Register SW as early as possible so beforeinstallprompt can fire before the
// user clicks the header install button (deferring to "load" caused a race).
// In DEV this only clears stale workers — it never registers (see sw-register).
if (typeof window !== "undefined") {
  void import("./sw-register").then(({ registerSW }) => registerSW());
}
