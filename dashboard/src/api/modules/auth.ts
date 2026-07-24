import { request } from "../request";

/**
 * Auth + setup module — adapted to octop's multi-user backend.
 *
 * Octop endpoints (spec §11.3):
 *  - GET  /api/setup/status         → { setup_required }
 *  - POST /api/setup/initial-admin  → 201 { id, username, role }
 *  - POST /api/auth/login           → { access_token, token_type, expires_in, user }
 *  - POST /api/auth/logout          → 204
 *  - GET  /api/auth/me              → { id, username, role, display_name }
 *  - POST /api/auth/change-password → 204
 *
 * The shape exported below is intentionally a superset that keeps a few
 * legacy fields populated (``setup_done``, ``enabled``, ``has_password``)
 * so existing finnie-derived components compile until they're replaced
 * by the octop settings editors in phase 14.6.
 */

export interface AuthStatus {
  /** True when no admin exists yet — UI must redirect to /setup. */
  setup_required: boolean;
  /** Legacy alias of ``!setup_required`` kept for compat. */
  setup_done: boolean;
  /** Octop always requires auth; kept true so legacy components don't unguard. */
  enabled: boolean;
  /** Legacy field — octop always uses passwords. */
  has_password: boolean;
  /** True when ~/.octop/octop-login.txt exists on the server (wizard-only). */
  wizard_password_exists: boolean;
  /** When false, the wizard skips the CLI bootstrap password step. */
  wizard_password_required: boolean;
  /** Absolute path to the one-time bootstrap password file on the server. */
  wizard_password_path?: string;
  /** True after `/setup/database` has bound the control-plane pool. */
  database_bound: boolean;
  /** Active control-plane driver when bound (`sqlite` | `postgresql`). */
  database_driver?: string | null;
}

export interface OctopUser {
  id: number;
  username: string;
  role: "admin" | "user";
  display_name: string | null;
  locale: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: OctopUser;
  /** Legacy alias for ``access_token`` so old callers using ``.token`` keep working. */
  token: string;
}

export interface SetupBody {
  username: string;
  password: string;
  display_name?: string | null;
}

interface RawSetupStatus {
  setup_required: boolean;
  wizard_password_required?: boolean;
  wizard_password_exists?: boolean;
  wizard_password_path?: string;
  database_bound?: boolean;
  database_driver?: string | null;
}

interface RawLoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: OctopUser;
}

export const authApi = {
  /** Probe whether the initial admin has been created. */
  getAuthStatus: async (): Promise<AuthStatus> => {
    const raw = await request<RawSetupStatus>("/setup/status");
    return {
      setup_required: raw.setup_required,
      setup_done: !raw.setup_required,
      enabled: true,
      has_password: true,
      wizard_password_exists: raw.wizard_password_exists ?? false,
      wizard_password_required: raw.wizard_password_required ?? true,
      wizard_password_path: raw.wizard_password_path,
      database_bound: raw.database_bound ?? false,
      database_driver: raw.database_driver ?? null,
    };
  },

  /** Bootstrap the first admin (only succeeds while user_manager is empty). */
  createInitialAdmin: (body: SetupBody) =>
    request<{ id: number; username: string; role: string }>(
      "/setup/initial-admin",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  /** Login — octop uses username + password. */
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const raw = await request<RawLoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    return { ...raw, token: raw.access_token };
  },

  /** Server-side logout (best-effort; client clears token regardless). */
  logout: () =>
    request<void>("/auth/logout", { method: "POST" }).catch(() => undefined),

  /** Get the current authenticated user. */
  me: () => request<OctopUser>("/auth/me"),

  /** Change current user's password. */
  changePassword: (oldPassword: string, newPassword: string) =>
    request<void>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword,
      }),
    }),

  /** Update the current user's display name (PATCH /auth/me). */
  updateProfile: (displayName: string | null) =>
    request<OctopUser>("/auth/me", {
      method: "PATCH",
      body: JSON.stringify({ display_name: displayName }),
    }),

  // --- Legacy stubs kept so finnie-era components compile ----------------
  // These call paths are removed in octop's data model; the actual
  // settings UI is rewritten in phase 14.6. Stubs return rejected
  // promises with a clear message to make accidental use loud.

  /** @deprecated Octop always requires auth — there is no first-time set step. */
  setPassword: (): Promise<never> =>
    Promise.reject(
      new Error("setPassword is not supported in octop; use change-password"),
    ),

  /** @deprecated Octop cannot disable auth. */
  disableAuth: (): Promise<never> =>
    Promise.reject(new Error("disableAuth is not supported in octop")),

  /** @deprecated Octop's setup wizard is single-step; nothing to mark done. */
  markSetupDone: (): Promise<{ ok: boolean }> => Promise.resolve({ ok: true }),
};
