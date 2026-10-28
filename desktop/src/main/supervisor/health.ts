/**
 * Sidecar readiness check (§3.3). Readiness is decided ONLY by a successful
 * ``/api/health`` response matching the Octop contract — never by log text.
 */

export interface HealthResponse {
  ok: boolean;
}

const HEALTH_TIMEOUT_MS = 30_000;
const POLL_INTERVAL_MS = 250;

export interface HealthProbe {
  (): Promise<{ ok: boolean; body?: unknown }>;
}

/** Validate the shape of an Octop ``/api/health`` JSON body. */
export function isHealthyBody(body: unknown): boolean {
  if (body === null || typeof body !== "object") return false;
  const record = body as Record<string, unknown>;
  return record.ok === true;
}

export async function waitForHealth(
  probe: HealthProbe,
  options: {
    timeoutMs?: number;
    intervalMs?: number;
    onExit?: () => boolean;
  } = {},
): Promise<boolean> {
  const timeoutMs = options.timeoutMs ?? HEALTH_TIMEOUT_MS;
  const intervalMs = options.intervalMs ?? POLL_INTERVAL_MS;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (options.onExit && options.onExit()) return false;
    try {
      const result = await probe();
      if (result.ok && isHealthyBody(result.body)) return true;
    } catch {
      // Not ready yet — keep polling until the deadline.
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}
