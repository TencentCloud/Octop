/**
 * One-shot soft reload when a Vite/webpack chunk fails to load after deploy.
 * sessionStorage guards against infinite reload loops.
 */

const RELOAD_FLAG_KEY = "octop:chunk-reload";

const CHUNK_ERROR_RE =
  /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk [\w.-]+ failed|ChunkLoadError|error loading dynamically imported module/i;

/**
 * A pending full-page navigation aborts every in-flight dynamic import, which
 * looks exactly like a post-deploy stale chunk. Reloading then would cancel
 * the navigation and strand the user on a blank page.
 */
let navigatingAway = false;

export function markNavigatingAway(): void {
  navigatingAway = true;
}

export function isChunkLoadError(error: unknown): boolean {
  if (error == null) return false;
  if (typeof error === "string") return CHUNK_ERROR_RE.test(error);
  if (error instanceof Error) {
    if (CHUNK_ERROR_RE.test(error.message)) return true;
    if (error.name === "ChunkLoadError") return true;
  }
  // Some browsers put the URL on TypeError without a useful message prefix.
  const text = String((error as { message?: unknown }).message ?? error);
  return CHUNK_ERROR_RE.test(text);
}

/** Drop SW + Cache Storage so the next load is not served a stale shell. */
export async function bustServiceWorkerAndReload(): Promise<void> {
  try {
    if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if (typeof caches !== "undefined") {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch {
    // Still reload — a soft refresh is better than staying on a blank page.
  }
  window.location.reload();
}

/** @returns true when a reload was triggered (caller should stop further handling). */
export function tryReloadOnStaleChunk(error: unknown): boolean {
  if (typeof window === "undefined") return false;
  if (navigatingAway) return false;
  if (!isChunkLoadError(error)) return false;

  try {
    if (sessionStorage.getItem(RELOAD_FLAG_KEY) === "1") {
      sessionStorage.removeItem(RELOAD_FLAG_KEY);
      return false;
    }
    sessionStorage.setItem(RELOAD_FLAG_KEY, "1");
  } catch {
    // Private mode / quota — still attempt a single reload without the guard.
  }

  console.warn("[Octop] Stale chunk detected; reloading once.", error);
  void bustServiceWorkerAndReload();
  return true;
}

/** Clear the one-shot flag after a successful boot so a later deploy can recover again. */
export function clearChunkReloadFlag(): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(RELOAD_FLAG_KEY);
  } catch {
    /* ignore */
  }
}

/** Install window-level listeners for chunk failures before React mounts. */
export function installChunkLoadRecovery(): void {
  if (typeof window === "undefined") return;

  window.addEventListener("pagehide", markNavigatingAway);
  // The tab may come back from bfcache instead of unloading (mobile app
  // switching), so the guard must not stick.
  window.addEventListener("pageshow", () => {
    navigatingAway = false;
  });

  window.addEventListener("unhandledrejection", (event) => {
    if (tryReloadOnStaleChunk(event.reason)) {
      event.preventDefault();
    }
  });

  window.addEventListener(
    "error",
    (event) => {
      const target = event.target;
      if (
        target instanceof HTMLScriptElement &&
        target.src.includes("/assets/")
      ) {
        tryReloadOnStaleChunk(
          new Error(
            `Failed to fetch dynamically imported module: ${target.src}`,
          ),
        );
        return;
      }
      if (
        target instanceof HTMLLinkElement &&
        target.href.includes("/assets/")
      ) {
        tryReloadOnStaleChunk(
          new Error(
            `Failed to fetch dynamically imported module: ${target.href}`,
          ),
        );
      }
    },
    true,
  );
}
