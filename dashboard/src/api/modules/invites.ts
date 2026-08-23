import { request } from "../request";

export type InviteStatus = "pending" | "used" | "expired" | "revoked";

export interface InviteRow {
  id: number;
  code: string;
  note: string | null;
  created_by: number;
  created_at: number;
  expires_at: number;
  used_at: number | null;
  used_by_user_id: number | null;
  revoked_at: number | null;
  status: InviteStatus;
  invite_path: string;
  invite_url: string;
}

export interface InviteCreateBody {
  note?: string | null;
  expires_in_days?: number;
}

export interface InviteRedeemBody {
  code: string;
  username: string;
  password: string;
  display_name?: string | null;
  email?: string | null;
}

export interface InviteRedeemResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: number;
    username: string;
    role: "admin" | "user";
    display_name: string | null;
    locale: string;
    permissions?: string[];
  };
}

/** Prefer the browser origin so copied links match how admins reach the UI. */
export function localInviteUrl(code: string): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/invite?code=${encodeURIComponent(code)}`;
}

export const invitesApi = {
  list: () => request<InviteRow[]>("/users/invites"),

  create: (body: InviteCreateBody = {}) =>
    request<InviteRow>("/users/invites", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  revoke: (id: number) =>
    request<InviteRow>(`/users/invites/${id}/revoke`, { method: "POST" }),

  validate: (code: string) =>
    request<{ ok: boolean; expires_at: number }>("/auth/invite/validate", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  redeem: (body: InviteRedeemBody) =>
    request<InviteRedeemResponse>("/auth/invite/redeem", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
