/**
 * Lightweight event bus for PWA lifecycle events.
 * Keeps sw-register.ts as a dynamic import (loaded after paint) while
 * still allowing synchronously-imported UI components to listen for events.
 *
 * Components listen via the DOM custom event "pwa:update-ready".
 * sw-register dispatches the same event — no direct module coupling needed.
 */

/** Apply the waiting Service Worker update. Delegates to sw-register at runtime. */
export async function applyUpdate(): Promise<void> {
  const { applyUpdate: apply } = await import("./sw-register");
  await apply();
}
