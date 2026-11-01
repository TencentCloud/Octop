import {
  clearSetupRequired,
  isSessionOnlyAuth,
  markSetupRequired,
  request,
  requestUpload,
  setAuthToken,
} from "../request";
import type {
  AuthenticationCredentialJSON,
  PublicKeyCreationOptionsJSON,
  PublicKeyRequestOptionsJSON,
  RegistrationCredentialJSON,
} from "../../utils/webauthn";

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

export interface SsoIdentity {
  kind: string;
}

export interface OctopUser {
  id: number;
  username: string;
  /** Role-template public id: admin | user | custom ULID. */
  role: string;
  display_name: string | null;
  locale: string;
  /** Module permission keys; admin responses include the full catalog. */
  permissions?: string[];
  sso_linked?: boolean;
  sso_kind?: string | null;
  /** Linked SSO providers (multi-identity). */
  sso_identities?: SsoIdentity[];
  has_password?: boolean;
  /** Preset character id. Empty means the built-in default portrait. */
  avatar_icon?: string | null;
  /** Uploaded portrait. Shown ahead of the preset when present. */
  avatar_url?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: OctopUser;
  /** Legacy alias for ``access_token`` so old callers using ``.token`` keep working. */
  token: string;
}

/** Second-factor methods offered after password when MFA is enrolled. */
export type MfaMethod = "totp" | "webauthn" | "recovery";

/** Password OK but MFA still required — no access_token. */
export interface MfaChallengeResponse {
  mfa_required: true;
  mfa_token: string;
  methods: MfaMethod[];
  user_hint?: string | null;
  locale?: string | null;
}

export type LoginResult = LoginResponse | MfaChallengeResponse;

export function isMfaChallenge(
  result: LoginResult,
): result is MfaChallengeResponse {
  return (result as MfaChallengeResponse).mfa_required === true;
}

/** Reauth grant for factor enrollment / disable / regenerate. */
export interface MfaReauthResponse {
  reauth_token: string;
  expires_in?: number;
}

export interface MfaPasskeyInfo {
  credential_id: string;
  name: string;
  created_at?: number | string | null;
  last_used_at?: number | string | null;
}

/**
 * Enrolled factors for the account-security UI.
 * Field names follow the SPEC; tolerate alternate backend aliases in getters.
 */
export interface MfaStatus {
  totp_verified: boolean;
  passkeys: MfaPasskeyInfo[];
  recovery_remaining: number;
  is_last_factor: boolean;
  /** False for SSO-only accounts (no local/LDAP password to prove). */
  can_enroll: boolean;
  has_password: boolean;
  sso_linked: boolean;
}

export interface MfaTotpBeginResponse {
  otpauth_uri: string;
  /** Optional server-rendered QR; prefer client QR from otpauth_uri. */
  qr_png_base64?: string | null;
  secret?: string | null;
}

/** Mutating MFA responses may mint a fresh access token (mfa_version bump). */
export interface MfaMutationResponse {
  access_token?: string;
  recovery_codes?: string[];
  user?: OctopUser;
}

const REAUTH_HEADER = "X-Octop-Reauth";

/** Replace the stored session JWT when a mutating MFA call returns one. */
export function adoptAccessToken(accessToken: string | undefined | null): void {
  if (!accessToken) return;
  setAuthToken(accessToken, !isSessionOnlyAuth());
}

function adoptFromMutation<T extends MfaMutationResponse>(body: T): T {
  adoptAccessToken(body.access_token);
  return body;
}

function reauthHeaders(reauthToken: string): HeadersInit {
  return { [REAUTH_HEADER]: reauthToken };
}

function normalizeMfaStatus(raw: Record<string, unknown>): MfaStatus {
  const passkeysRaw = Array.isArray(raw.passkeys) ? raw.passkeys : [];
  const passkeys: MfaPasskeyInfo[] = [];
  for (const item of passkeysRaw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const credentialId =
      typeof row.credential_id === "string"
        ? row.credential_id
        : typeof row.id === "string"
        ? row.id
        : "";
    if (!credentialId) continue;
    passkeys.push({
      credential_id: credentialId,
      // Empty name is fine — UI shows a localized default (never raw credential id).
      name: typeof row.name === "string" ? row.name.trim() : "",
      created_at:
        typeof row.created_at === "number" || typeof row.created_at === "string"
          ? row.created_at
          : null,
      last_used_at:
        typeof row.last_used_at === "number" ||
        typeof row.last_used_at === "string"
          ? row.last_used_at
          : null,
    });
  }

  // Backend shape: { totp: { enabled, pending }, recovery_codes_remaining, … }
  const totpObj =
    raw.totp && typeof raw.totp === "object"
      ? (raw.totp as Record<string, unknown>)
      : null;
  const totpVerified = Boolean(
    totpObj?.enabled ?? raw.totp_verified ?? raw.totp_enabled ?? raw.has_totp,
  );
  const recoveryRemaining = Number(
    raw.recovery_codes_remaining ?? raw.recovery_remaining ?? 0,
  );
  return {
    totp_verified: totpVerified,
    passkeys,
    recovery_remaining: Number.isFinite(recoveryRemaining)
      ? recoveryRemaining
      : 0,
    is_last_factor: Boolean(raw.is_last_factor),
    // Enrollment eligibility comes from /auth/me (has_password / SSO); status
    // itself does not currently expose these flags.
    can_enroll: raw.can_enroll !== false,
    has_password: Boolean(raw.has_password),
    sso_linked: Boolean(raw.sso_linked),
  };
}

export interface PublicCaptcha {
  provider: string;
  site_key?: string;
}

export interface OidcStatus {
  enabled: boolean;
  display_name: string;
}

export interface OauthProviderStatus {
  kind: string;
  display_name: string;
  enabled: boolean;
}

export interface OauthStatus {
  providers: OauthProviderStatus[];
}

/** Public LDAP login availability probe (no auth required). */
export interface LdapStatus {
  enabled: boolean;
  display_name: string;
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
  access_token?: string;
  token_type?: string;
  expires_in?: number;
  user?: OctopUser;
  mfa_required?: boolean;
  mfa_token?: string;
  methods?: MfaMethod[];
  user_hint?: string | null;
  locale?: string | null;
}

function toLoginResult(raw: RawLoginResponse): LoginResult {
  if (raw.mfa_required === true && raw.mfa_token) {
    return {
      mfa_required: true,
      mfa_token: raw.mfa_token,
      methods: Array.isArray(raw.methods) ? raw.methods : [],
      user_hint: raw.user_hint ?? null,
      locale: raw.locale ?? null,
    };
  }
  if (!raw.access_token || !raw.user) {
    throw new Error("Invalid login response");
  }
  return {
    access_token: raw.access_token,
    token_type: raw.token_type ?? "bearer",
    expires_in: raw.expires_in ?? 0,
    user: raw.user,
    token: raw.access_token,
  };
}

/** Coalesce AuthGuard / Login / Setup probing the same endpoint in parallel. */
let statusInFlight: Promise<AuthStatus> | null = null;

/** Drop any in-flight setup-status probe (e.g. after creating the admin). */
export function invalidateAuthStatusCache(): void {
  statusInFlight = null;
}

function applySetupFlags(status: AuthStatus): AuthStatus {
  if (status.setup_required) {
    markSetupRequired();
  } else {
    clearSetupRequired();
  }
  return status;
}

export const authApi = {
  /** Probe whether the initial admin has been created. */
  getAuthStatus: async (): Promise<AuthStatus> => {
    if (statusInFlight) return statusInFlight;

    statusInFlight = (async () => {
      try {
        const raw = await request<RawSetupStatus>("/setup/status");
        const value: AuthStatus = {
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
        return applySetupFlags(value);
      } finally {
        statusInFlight = null;
      }
    })();

    return statusInFlight;
  },

  /** Bootstrap the first admin (only succeeds while user_manager is empty). */
  createInitialAdmin: async (body: SetupBody) => {
    const result = await request<{
      id: number;
      username: string;
      role: string;
    }>("/setup/initial-admin", {
      method: "POST",
      body: JSON.stringify(body),
    });
    invalidateAuthStatusCache();
    clearSetupRequired();
    return result;
  },

  /** Public captcha widget config for the login form. */
  getCaptcha: () => request<PublicCaptcha>("/auth/captcha"),

  /** Login — octop uses username + password. May return ``mfa_required``. */
  login: async (
    username: string,
    password: string,
    captchaToken?: string,
  ): Promise<LoginResult> => {
    const raw = await request<RawLoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(
        captchaToken
          ? { username, password, captcha_token: captchaToken }
          : { username, password },
      ),
    });
    return toLoginResult(raw);
  },

  /** Return whether the configured OIDC provider can accept logins. */
  getOidcStatus: () => request<OidcStatus>("/auth/oidc/status"),

  /** Return enabled dashboard SSO providers for the login page. */
  getOauthStatus: () => request<OauthStatus>("/auth/oauth/status"),

  /** Return whether directory (LDAP) logins are available, and its label. */
  getLdapStatus: () => request<LdapStatus>("/auth/ldap/status"),

  /** Start an OIDC authorization-code login flow. */
  startOidc: (redirect_after?: string) =>
    request<{ authorization_url: string }>("/auth/oidc/start", {
      method: "POST",
      body: JSON.stringify({ redirect_after }),
    }),

  /** Start an OAuth/OIDC authorization-code login flow by provider kind. */
  startOauth: (kind: string, redirect_after?: string) =>
    request<{ authorization_url: string }>("/auth/oauth/start", {
      method: "POST",
      body: JSON.stringify({ kind, redirect_after }),
    }),

  /** Start an OAuth flow that binds the identity to the current user. */
  startOauthBind: (kind: string, redirect_after?: string) =>
    request<{ authorization_url: string }>("/auth/oauth/bind/start", {
      method: "POST",
      body: JSON.stringify({ kind, redirect_after }),
    }),

  /** Unlink one SSO identity by kind. Requires a local password when it is the last login method. */
  unbindOauth: (kind: string) =>
    request<OctopUser>("/auth/oauth/unbind", {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),

  /** Exchange the one-time browser code for the standard JWT login response. */
  exchangeOidcCode: async (code: string): Promise<LoginResponse> => {
    const raw = await request<RawLoginResponse>("/auth/oidc/exchange", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    const result = toLoginResult(raw);
    if (isMfaChallenge(result)) {
      // SSO paths do not use Octop MFA; treat as protocol error if seen.
      throw new Error("Unexpected MFA challenge on SSO exchange");
    }
    return result;
  },

  // --- MFA / passkeys (SPEC contract; backend may land in parallel) --------

  /** Prove password (or LDAP bind) before factor enrollment / disable. */
  mfaReauth: (password: string) =>
    request<MfaReauthResponse>("/auth/mfa/reauth", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  /** Complete MFA after password login (TOTP / recovery / passkey assertion). */
  mfaVerify: async (body: {
    mfa_token: string;
    method: MfaMethod;
    code?: string;
    credential?: AuthenticationCredentialJSON;
  }): Promise<LoginResponse> => {
    const raw = await request<RawLoginResponse>("/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const result = toLoginResult(raw);
    if (isMfaChallenge(result)) {
      throw new Error("Unexpected MFA challenge on verify");
    }
    return result;
  },

  /** Assertion options for passkey-as-2FA (requires mfa_token). */
  mfaPasskeyOptions: (mfaToken: string) =>
    request<PublicKeyRequestOptionsJSON>("/auth/mfa/passkey/options", {
      method: "POST",
      body: JSON.stringify({ mfa_token: mfaToken }),
    }),

  /** Passwordless passkey — begin ceremony (Conditional UI / modal). */
  passkeyLoginOptions: () =>
    request<PublicKeyRequestOptionsJSON>("/auth/passkey/login/options", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  /** Passwordless passkey — finish; issues access token (satisfies MFA). */
  passkeyLoginVerify: async (
    credential: AuthenticationCredentialJSON,
  ): Promise<LoginResponse> => {
    const raw = await request<RawLoginResponse>("/auth/passkey/login/verify", {
      method: "POST",
      body: JSON.stringify({ credential }),
    });
    const result = toLoginResult(raw);
    if (isMfaChallenge(result)) {
      throw new Error("Unexpected MFA challenge on passkey login");
    }
    return result;
  },

  /** Current MFA enrollment status (never secrets). */
  mfaStatus: async (): Promise<MfaStatus> => {
    const raw = await request<Record<string, unknown>>("/auth/mfa/status");
    return normalizeMfaStatus(raw);
  },

  mfaTotpBegin: (reauthToken: string) =>
    request<MfaTotpBeginResponse>("/auth/mfa/totp/begin", {
      method: "POST",
      body: JSON.stringify({}),
      headers: reauthHeaders(reauthToken),
    }),

  mfaTotpConfirm: async (reauthToken: string, code: string) => {
    const body = await request<MfaMutationResponse>("/auth/mfa/totp/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
      headers: reauthHeaders(reauthToken),
    });
    return adoptFromMutation(body);
  },

  mfaTotpDisable: async (reauthToken: string) => {
    const body = await request<MfaMutationResponse>("/auth/mfa/totp", {
      method: "DELETE",
      headers: reauthHeaders(reauthToken),
    });
    return adoptFromMutation(body);
  },

  mfaPasskeyRegisterOptions: (reauthToken: string) =>
    request<PublicKeyCreationOptionsJSON>(
      "/auth/mfa/passkey/register/options",
      {
        method: "POST",
        body: JSON.stringify({}),
        headers: reauthHeaders(reauthToken),
      },
    ),

  mfaPasskeyRegisterVerify: async (
    reauthToken: string,
    credential: RegistrationCredentialJSON,
    name?: string,
  ) => {
    const body = await request<MfaMutationResponse>(
      "/auth/mfa/passkey/register/verify",
      {
        method: "POST",
        body: JSON.stringify({ credential, name }),
        headers: reauthHeaders(reauthToken),
      },
    );
    return adoptFromMutation(body);
  },

  mfaPasskeyRemove: async (reauthToken: string, credentialId: string) => {
    const body = await request<MfaMutationResponse>(
      `/auth/mfa/passkey/${encodeURIComponent(credentialId)}`,
      {
        method: "DELETE",
        headers: reauthHeaders(reauthToken),
      },
    );
    return adoptFromMutation(body);
  },

  mfaRecoveryRegenerate: async (reauthToken: string) => {
    const body = await request<MfaMutationResponse>(
      "/auth/mfa/recovery/regenerate",
      {
        method: "POST",
        body: JSON.stringify({}),
        headers: reauthHeaders(reauthToken),
      },
    );
    return adoptFromMutation(body);
  },

  /**
   * Admin: clear target user's MFA factors.
   * Backend returns 204 (no body); target ``mfa_version`` bump invalidates their sessions.
   */
  adminResetMfa: (userId: number) =>
    request<void>(`/users/${userId}/mfa`, { method: "DELETE" }),

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

  /** Choose a preset icon. Null restores the built-in default and clears an upload. */
  setAvatarIcon: (icon: string | null) =>
    request<OctopUser>("/auth/me", {
      method: "PATCH",
      body: JSON.stringify({ avatar_icon: icon }),
    }),

  uploadAvatar: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return requestUpload<{ avatar_url: string | null }>(
      "/auth/me/avatar",
      body,
    );
  },

  deleteAvatar: () => request<void>("/auth/me/avatar", { method: "DELETE" }),

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
