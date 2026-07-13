/**
 * Thin client for the 4-step setup wizard endpoints.
 *
 * Lives outside the global auth flow because the wizard token is a
 * one-shot, short-TTL bearer that must not pollute the regular
 * Authorization header path.
 */

import { request } from "../../api/request";

export interface VerifyResponse {
  wizard_token: string;
  expires_in: number;
}

export interface CreateAdminBody {
  username: string;
  display_name: string | null;
  password: string;
  /** UI locale for the initial admin (zh|en). */
  locale?: string;
}

export interface WizardProviderModel {
  id: string;
  name: string;
  enabled: boolean;
  input: string[];
  thinking: null;
  reasoning?: boolean;
}

export interface ProviderDraft {
  name: string; // Provider display name
  type: string; // kind field (openai, anthropic, etc.)
  api_key: string;
  base_url?: string;
  models: WizardProviderModel[];
  extras?: Record<string, unknown>;
}

const TOKEN_KEY = "octop:wizard-token";
const SETUP_JWT_KEY = "octop:setup-jwt";
const DRAFT_KEY = "octop:wizard-draft";
const STEP_KEY = "octop:wizard-step";

export const STEP_PASSWORD = 0;
export const STEP_ADMIN = 1;
export const STEP_MODEL = 2;
export const STEP_FINISH = 3;

export const wizardSession = {
  saveToken(token: string): void {
    sessionStorage.setItem(TOKEN_KEY, token);
  },
  loadToken(): string | null {
    return sessionStorage.getItem(TOKEN_KEY);
  },
  saveSetupJwt(token: string): void {
    sessionStorage.setItem(SETUP_JWT_KEY, token);
  },
  loadSetupJwt(): string | null {
    return sessionStorage.getItem(SETUP_JWT_KEY);
  },
  clearSetupJwt(): void {
    sessionStorage.removeItem(SETUP_JWT_KEY);
  },
  clearToken(): void {
    sessionStorage.removeItem(TOKEN_KEY);
  },
  saveStep(step: number): void {
    sessionStorage.setItem(STEP_KEY, String(step));
  },
  loadStep(): number | null {
    const raw = sessionStorage.getItem(STEP_KEY);
    if (raw == null) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  },
  saveDraft(draft: { adminUsername?: string; provider?: ProviderDraft }): void {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  },
  loadDraft(): { adminUsername?: string; provider?: ProviderDraft } {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return {};
    try {
      return JSON.parse(raw) as {
        adminUsername?: string;
        provider?: ProviderDraft;
      };
    } catch {
      return {};
    }
  },
  clearAll(): void {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(SETUP_JWT_KEY);
    sessionStorage.removeItem(DRAFT_KEY);
    sessionStorage.removeItem(STEP_KEY);
  },
};

function bearer(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export const wizardApi = {
  begin: () =>
    request<VerifyResponse>("/setup/begin", {
      method: "POST",
    }),

  verifyPassword: (password: string) =>
    request<VerifyResponse>("/setup/verify-password", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  validateToken: (wizardToken: string) =>
    request<{ valid: boolean }>("/setup/validate-token", {
      headers: bearer(wizardToken),
    }),

  createAdmin: (body: CreateAdminBody, wizardToken: string) =>
    request<{
      id: number;
      username: string;
      role: string;
      access_token: string;
      expires_in: number;
    }>("/setup/initial-admin", {
      method: "POST",
      body: JSON.stringify(body),
      headers: bearer(wizardToken),
    }),

  resumeWizard: () =>
    request<VerifyResponse>("/setup/resume-wizard", {
      method: "POST",
    }),

  finish: (
    body: { provider_draft: ProviderDraft | null },
    wizardToken: string,
  ) =>
    request<{ ok: boolean }>("/setup/finish", {
      method: "POST",
      body: JSON.stringify(body),
      headers: bearer(wizardToken),
    }),

  testProvider: (
    body: {
      name: string;
      type: string;
      api_key: string;
      base_url?: string;
      model_id: string;
    },
    wizardToken: string,
  ) =>
    request<{ ok: boolean; latency_ms?: number; error?: string }>(
      "/setup/test-provider",
      {
        method: "POST",
        body: JSON.stringify(body),
        headers: bearer(wizardToken),
      },
    ),
};

/**
 * Resolve a Bearer token for setup provider probes.
 * Prefers a valid wizard token, then the admin JWT issued at initial-admin,
 * then a freshly resumed wizard token.
 */
export async function resolveSetupProbeToken(): Promise<string | null> {
  const wizardToken = wizardSession.loadToken();
  if (wizardToken) {
    try {
      const { valid } = await wizardApi.validateToken(wizardToken);
      if (valid) return wizardToken;
    } catch {
      /* fall through */
    }
  }

  const setupJwt = wizardSession.loadSetupJwt();
  if (setupJwt) return setupJwt;

  try {
    const resumed = await wizardApi.resumeWizard();
    wizardSession.saveToken(resumed.wizard_token);
    return resumed.wizard_token;
  } catch {
    return null;
  }
}
