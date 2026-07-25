/**
 * Service Worker registration and lifecycle management.
 *
 * Production (all browsers including Chrome / Safari):
 *   - Register `/sw.js` with workbox `skipWaiting: false` (vite.config).
 *   - Never auto `location.reload()` on `controllerchange` — that pattern
 *     caused full-page refresh loops (especially WebKit). Updates apply only
 *     when the user clicks the banner → `applyUpdate()`.
 *
 * Dev:
 *   - Do not register. Clear any leftover production SW on the same origin
 *     so Vite HMR and an old worker do not fight over navigations.
 */

let pendingRegistration: ServiceWorkerRegistration | null = null;
let applyingUpdate = false;

function notifyUpdateReady(): void {
  window.dispatchEvent(new CustomEvent("pwa:update-ready"));
}

async function unregisterAllServiceWorkers(): Promise<void> {
  const regs = await navigator.serviceWorker.getRegistrations();
  await Promise.all(regs.map((r) => r.unregister()));
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
  }
}

/**
 * Apply a waiting Service Worker update and reload once.
 * Only called from explicit UI actions (PwaUpdatePrompt).
 */
export function applyUpdate(): void {
  if (applyingUpdate) return;
  applyingUpdate = true;
  if (pendingRegistration?.waiting) {
    pendingRegistration.waiting.postMessage({ type: "SKIP_WAITING" });
  }
  window.location.reload();
}

export async function registerSW(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;

  if (import.meta.env.DEV) {
    try {
      await unregisterAllServiceWorkers();
    } catch (err) {
      console.warn("[SW] Dev cleanup failed:", err);
    }
    return;
  }

  try {
    const registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
    });

    // Intentionally no controllerchange → location.reload() listener.
    // Chrome and Safari both pick up new assets via applyUpdate() instead.

    if (registration.waiting) {
      pendingRegistration = registration;
      notifyUpdateReady();
    }

    registration.addEventListener("updatefound", () => {
      const installing = registration.installing;
      if (!installing) return;
      installing.addEventListener("statechange", () => {
        if (
          installing.state === "installed" &&
          navigator.serviceWorker.controller
        ) {
          pendingRegistration = registration;
          notifyUpdateReady();
        }
      });
    });

    setInterval(
      () => {
        void registration.update();
      },
      60 * 60 * 1000,
    );
  } catch (err) {
    console.error("[SW] Registration failed:", err);
  }
}
