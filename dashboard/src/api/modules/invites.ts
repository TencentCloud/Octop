import { request } from "../request";

export type InviteStatus = "active" | "disabled" | "expired";

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
  enabled: boolean;
  use_count: number;
  max_uses: number | null;
  invite_path: string;
  invite_url: string;
  role_name?: string | null;
  /** Role-template public id applied at redeem time. */
  role?: string | null;
}

export interface InviteCreateBody {
  note?: string | null;
  expires_in_days?: number;
  max_uses?: number;
  role?: string | null;
}

export interface InviteUserRow {
  id: number;
  username: string;
  display_name: string | null;
  email: string | null;
  created_at: number;
  redeemed_at: number;
}

export interface InviteUsersResponse {
  users: InviteUserRow[];
  total: number;
  page: number;
  page_size: number;
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
    role: string;
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

  setEnabled: (id: number, enabled: boolean) =>
    request<InviteRow>(`/users/invites/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),

  users: (id: number, page = 1, pageSize = 20) =>
    request<InviteUsersResponse>(
      `/users/invites/${id}/users?page=${page}&page_size=${pageSize}`,
    ),

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
