import type { IssuedSession } from "../../shared/ipc-contract";
import type { DeviceCredentialStore } from "./device-credential";

/**
 * Trades the stored device credential for a JWT (§7 accounts).
 *
 * Runs in the main process only: the renderer asks for a token, never for the
 * credential. All three calls go to the sidecar over loopback, so a renewal
 * never leaves the machine.
 */

export interface DeviceSessionOptions {
  store: DeviceCredentialStore;
  /** Loopback base URL of the sidecar, or null while it is down / being replaced. */
  baseUrl: () => string | null;
  /** Device label recorded server-side, e.g. "darwin-arm64". */
  label: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

interface JsonResponse {
  status: number;
  data: unknown;
}

export class DeviceSessionClient {
  // Assigned field-by-field: parameter properties are not supported by the
  // strip-only TypeScript loader the tests use.
  private readonly options: DeviceSessionOptions;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(options: DeviceSessionOptions) {
    this.options = options;
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.timeoutMs = options.timeoutMs ?? 5_000;
  }

  /**
   * Bind the stored credential to the signed-in user.
   *
   * Called whenever the renderer has a valid JWT (first setup, a later login, or
   * any request after an app upgrade) so an install that predates this feature
   * registers itself without user action.
   */
  async register(accessToken: string): Promise<boolean> {
    if (!accessToken) return false;
    const { secret } = await this.options.store.getOrCreate();
    const res = await this.post(
      "/api/auth/device/register",
      { device_token: secret, label: this.options.label },
      accessToken,
    );
    if (res.status !== 200) {
      console.warn(`[desktop] device registration returned ${res.status}`);
      return false;
    }
    return true;
  }

  /** Mint a fresh JWT, or null when there is no usable credential. */
  async renew(): Promise<IssuedSession | null> {
    const secret = await this.options.store.read();
    if (!secret) return null;
    const res = await this.post("/api/auth/device/token", { device_token: secret });
    if (res.status !== 200) {
      console.warn(`[desktop] device session renewal returned ${res.status}`);
      return null;
    }
    const body = res.data as Partial<IssuedSession> | null;
    if (!body || typeof body.access_token !== "string" || !body.access_token) return null;
    return {
      access_token: body.access_token,
      expires_in: typeof body.expires_in === "number" ? body.expires_in : 0,
    };
  }

  /** Stop future renewals for this install (the JWT in hand keeps working). */
  async revoke(accessToken: string): Promise<boolean> {
    if (!accessToken) return false;
    const res = await this.post("/api/auth/device/revoke", {}, accessToken);
    if (res.status !== 200) return false;
    await this.options.store.clear();
    return true;
  }

  private async post(path: string, body: unknown, accessToken?: string): Promise<JsonResponse> {
    const base = this.options.baseUrl();
    if (!base) return { status: 0, data: null };
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    try {
      const res = await this.fetchImpl(base + path, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      let data: unknown = null;
      try {
        data = await res.json();
      } catch {
        data = null;
      }
      return { status: res.status, data };
    } catch (err) {
      // Sidecar restarting, port not up yet, or a slow machine: the caller just
      // falls back to the login screen. Log the message only — a stack trace on
      // every boot attempt would drown the desktop log.
      const detail = err instanceof Error ? err.message : String(err);
      console.warn(`[desktop] ${path} failed: ${detail}`);
      return { status: 0, data: null };
    }
  }
}
