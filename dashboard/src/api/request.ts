import { getApiUrl } from "./config";
import i18n from "../i18n";

const AUTH_TOKEN_KEY = "auth_token";

/** Response header used by the server for JWT sliding renewal. */
export const ACCESS_TOKEN_RESPONSE_HEADER = "X-Octop-Access-Token";

/** Save JWT token to localStorage */
export function setAuthToken(token: string) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

/** Get JWT token from localStorage */
export function getAuthToken(): string {
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

/** Remove JWT token from localStorage */
export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem("octop:active-agent");
  setActiveAgentId(null);
}

/** Persist a sliding-renewed access token from an API response, if present. */
export function applyRenewedAccessToken(response: Response): void {
  const renewed = response.headers.get(ACCESS_TOKEN_RESPONSE_HEADER);
  if (renewed) {
    setAuthToken(renewed);
  }
}

let _redirectingToSetup = false;

/**
 * Hard-redirect once when the backend reports the wizard isn't done.
 * The flag prevents N parallel API calls from each issuing a navigate.
 */
function handleSetupRequired(): void {
  if (_redirectingToSetup) return;
  // Already on a public bootstrap route — a 503 from a background prefetch
  // must not reload the page or we loop forever.
  const path = window.location.pathname;
  if (path.startsWith("/setup") || path.startsWith("/login")) {
    return;
  }
  _redirectingToSetup = true;
  // Full reload drops any in-flight React state.
  window.location.replace("/setup");
}

/**
 * Inspect a response for the lockdown signal (503 + body
 * `{setup_required: true}`) and trigger a one-shot navigate to /setup.
 *
 * Returns ``true`` when the response matched and the caller should
 * abort the normal success/error path. The wizard's own ``/setup/*``
 * calls are exempt to avoid redirect loops.
 */
async function check503ForSetupRequired(
  path: string,
  response: Response,
): Promise<boolean> {
  if (response.status !== 503) return false;
  let body: unknown = null;
  try {
    body = await response.clone().json();
  } catch {
    /* not JSON — fall through to the standard error path. */
    return false;
  }
  if (
    body &&
    typeof body === "object" &&
    (body as Record<string, unknown>).setup_required === true
  ) {
    if (!path.startsWith("/setup/")) {
      handleSetupRequired();
    }
    return true;
  }
  return false;
}

/**
 * Active agent id — populated by ``AgentProvider`` in ``context/AgentContext.tsx``
 * whenever the user picks a new agent in the top-bar switcher. Stored at
 * module scope so plain functions like ``request()`` can read it without
 * threading a context through every call site.
 *
 * The value is ALSO mirrored to ``localStorage["octop:active-agent"]`` by
 * the provider — but the source of truth at request time is this variable
 * so reactions stay synchronous.
 */
let activeAgentId: string | null = null;

/** Setter used by AgentProvider; also clears when ``null``. */
export function setActiveAgentId(id: string | null) {
  activeAgentId = id;
}

/** Read the active agent id (e.g. from non-React code). */
export function getActiveAgentId(): string | null {
  return activeAgentId;
}

/**
 * Decide whether a request path is "agent-scoped" — i.e. talking to a
 * concrete agent's resource — and therefore should carry the
 * ``X-Octop-Agent-Id`` header. Health, admin, auth, setup, providers, and
 * personas don't need it.
 */
function isAgentScopedPath(path: string): boolean {
  // Match `/agents/<id>/...` (one trailing segment after the id).
  // The path passed to request() is stripped of the /api prefix.
  if (/^\/agents\/[^/]+(\/|$)/.test(path)) return true;
  // MBTI endpoints that read/write the active agent's persona config.
  if (/^\/mbti\//.test(path)) return true;
  return false;
}

function buildHeaders(path: string, extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Accept-Language": i18n.language?.startsWith("zh") ? "zh" : "en",
  };

  // Apply the global JWT first; the caller's `extra` (including a
  // wizard token) can still override it below.
  const token = getAuthToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  // Caller-supplied headers win — needed so the setup wizard can pass
  // its short-TTL Bearer without being stomped by a stale localStorage
  // JWT.
  if (extra) {
    const extraEntries =
      extra instanceof Headers
        ? Array.from(extra.entries())
        : Array.isArray(extra)
        ? extra
        : Object.entries(extra);
    for (const [k, v] of extraEntries) {
      headers[k] = String(v);
    }
  }

  if (
    activeAgentId &&
    isAgentScopedPath(path) &&
    !headers["X-Octop-Agent-Id"]
  ) {
    headers["X-Octop-Agent-Id"] = activeAgentId;
  }

  return headers;
}

/**
 * Build auth-only headers (no Content-Type — let the browser set it for FormData).
 */
function buildAuthHeaders(path: string): Record<string, string> {
  const headers: Record<string, string> = {
    "Accept-Language": i18n.language?.startsWith("zh") ? "zh" : "en",
  };
  const token = getAuthToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (
    activeAgentId &&
    isAgentScopedPath(path) &&
    !headers["X-Octop-Agent-Id"]
  ) {
    headers["X-Octop-Agent-Id"] = activeAgentId;
  }
  return headers;
}

/**
 * Handle 401 responses: clear token, redirect to login, and throw.
 * Shared by request(), requestBlob(), and requestUpload().
 */
async function throwIfUnauthorized(
  path: string,
  response: Response,
): Promise<void> {
  if (response.status !== 401 || path.startsWith("/auth/")) {
    return;
  }
  clearAuthToken();
  if (
    !window.location.pathname.startsWith("/setup") &&
    !window.location.pathname.startsWith("/login")
  ) {
    window.location.href = "/login";
  }
  let message = "Unauthorized";
  if (path.startsWith("/setup/")) {
    try {
      const body = (await response.clone().json()) as {
        error?: { message?: string };
      };
      if (body?.error?.message) {
        message = body.error.message;
      }
    } catch {
      /* keep generic message */
    }
  }
  throw new Error(message);
}

export async function request<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = getApiUrl(path);

  const headers = buildHeaders(path, options.headers);

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (await check503ForSetupRequired(path, response)) {
    throw new Error("Setup required — redirecting to /setup");
  }

  await throwIfUnauthorized(path, response);
  applyRenewedAccessToken(response);

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `Request failed: ${response.status} ${response.statusText}${
        text ? ` - ${text}` : ""
      }`,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return (await response.text()) as unknown as T;
  }

  return (await response.json()) as T;
}

/**
 * Download a binary resource as a Blob.
 */
export async function requestBlob(
  path: string,
  options: RequestInit = {},
): Promise<Blob> {
  const url = getApiUrl(path);
  const headers = buildAuthHeaders(path);
  const response = await fetch(url, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string>) },
  });

  if (await check503ForSetupRequired(path, response)) {
    throw new Error("Setup required — redirecting to /setup");
  }

  await throwIfUnauthorized(path, response);
  applyRenewedAccessToken(response);

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `Request failed: ${response.status} ${response.statusText}${
        text ? ` - ${text}` : ""
      }`,
    );
  }

  return response.blob();
}

/**
 * Upload a FormData payload (no explicit Content-Type — browser handles boundary).
 */
export async function requestUpload<T = unknown>(
  path: string,
  body: FormData,
  options: RequestInit = {},
): Promise<T> {
  const url = getApiUrl(path);
  const headers = buildAuthHeaders(path);

  const response = await fetch(url, {
    method: "POST",
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string>) },
    body,
  });

  if (await check503ForSetupRequired(path, response)) {
    throw new Error("Setup required — redirecting to /setup");
  }

  await throwIfUnauthorized(path, response);
  applyRenewedAccessToken(response);

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    let detail = `Upload failed: ${response.status}`;
    try {
      const json = JSON.parse(text);
      if (json.detail) detail = json.detail;
    } catch {
      if (text) detail = text;
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}
