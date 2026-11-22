/** Memory sharing: proxy to the standalone octop-memory admin API. */

import { request } from "../request";

export interface SharingSession {
  connected: boolean;
  space_id?: string;
  scopes?: string[];
  expires_at?: string;
}

export interface SharingToken {
  token_id: string;
  client_name: string;
  scopes: string[];
  token_hint: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface SharingTokenCreated {
  token_id: string;
  client_name: string;
  scopes: string[];
  token: string;
  token_hint: string;
}

export interface SharingClient {
  client: string;
  count: number;
  last_seen: string | null;
  tokens: string[];
}

export const memorySharingApi = {
  status: () => request<SharingSession>("/memory-sharing/session"),

  connect: (code: string) =>
    request<SharingSession>("/memory-sharing/session", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  disconnect: () =>
    request<SharingSession>("/memory-sharing/session", { method: "DELETE" }),

  tokens: () => request<{ tokens: SharingToken[] }>("/memory-sharing/tokens"),

  createToken: (clientName: string, scopes: string[]) =>
    request<SharingTokenCreated>("/memory-sharing/tokens", {
      method: "POST",
      body: JSON.stringify({ client_name: clientName, scopes }),
    }),

  rotateToken: (tokenId: string) =>
    request<SharingTokenCreated>(
      `/memory-sharing/tokens/${encodeURIComponent(tokenId)}/rotate`,
      { method: "POST" },
    ),

  revokeToken: (tokenId: string) =>
    request<{ revoked: boolean }>(
      `/memory-sharing/tokens/${encodeURIComponent(tokenId)}`,
      { method: "DELETE" },
    ),

  clients: () =>
    request<{ clients: SharingClient[] }>("/memory-sharing/clients"),

  binding: (agentId: string) =>
    request<{ agent_id: string; space_id: string | null }>(
      `/memory-sharing/binding/${encodeURIComponent(agentId)}`,
    ),

  bind: (agentId: string, spaceId: string) =>
    request<{ agent_id: string; space_id: string }>("/memory-sharing/binding", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, space_id: spaceId }),
    }),
};

export interface GroupToken extends SharingToken {
  group_id: string;
  token?: string;
}

export interface AccessGroup {
  group_id: string;
  name: string;
  space_id: string;
  scopes: string[];
  created_at: string;
  tokens: GroupToken[];
}

export interface AccessGroupCreated {
  group_id: string;
  name: string;
  space_id: string;
  tokens: (GroupToken & { token: string })[];
}

export const memorySharingGroupsApi = {
  list: () =>
    request<{ groups: AccessGroup[] }>("/memory-sharing/access-groups"),

  create: (name: string, clients: string[], scopes: string[]) =>
    request<AccessGroupCreated>("/memory-sharing/access-groups", {
      method: "POST",
      body: JSON.stringify({ name, clients, scopes }),
    }),

  rotate: (groupId: string, client: string) =>
    request<GroupToken & { token: string }>(
      `/memory-sharing/access-groups/${encodeURIComponent(
        groupId,
      )}/clients/${encodeURIComponent(client)}/rotate`,
      { method: "POST" },
    ),

  disable: (groupId: string, client: string) =>
    request<{ revoked: boolean; client_name: string }>(
      `/memory-sharing/access-groups/${encodeURIComponent(
        groupId,
      )}/clients/${encodeURIComponent(client)}`,
      { method: "DELETE" },
    ),

  enable: (groupId: string, client: string) =>
    request<GroupToken & { token: string }>(
      `/memory-sharing/access-groups/${encodeURIComponent(groupId)}/clients`,
      { method: "POST", body: JSON.stringify({ client_name: client }) },
    ),
};
