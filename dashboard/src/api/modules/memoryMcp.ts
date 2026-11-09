/**
 * memoryMcp — user-level API tokens for the memory MCP server.
 *
 * Routes live under ``/api/memory-mcp/tokens`` (``octop.api.routers.memory_mcp``).
 * Tokens are personal: a caller acts as the user the token was issued to, so
 * ``X-Octop-User-Id`` is never trusted. Only the digest is stored server-side;
 * the plaintext value is returned exactly once, at creation.
 *
 * Wire shapes are snake_case on purpose, mirroring the backend ``TokenOut`` /
 * ``TokenCreated`` models.
 */

import { request } from "../request";

export interface MemoryMcpToken {
  /** Public id used to revoke the token. */
  token_id: string;
  /** Client name supplied at creation, e.g. ``codex@macbook``. */
  name: string;
  /** Expert (agent) allow-list; null means every expert the user can access. */
  expert_ids: string[] | null;
  /** Masked value safe to display, e.g. ``omcp_…abcd``. */
  token_hint: string;
  /** ISO-8601 UTC. */
  created_at: string;
  /** ISO-8601 UTC, or null when the token has never been used. */
  last_used_at: string | null;
  /** ISO-8601 UTC once revoked; null while the token is active. */
  revoked_at: string | null;
}

/** Successful create result: the token row plus its one-time plaintext. */
export interface MemoryMcpTokenCreated {
  token: MemoryMcpToken;
  plaintext: string;
}

export interface CreateMemoryMcpTokenBody {
  name: string;
  /** Omit / null to allow every expert the issuing user can access. */
  expert_ids: string[] | null;
}

export interface RevokeMemoryMcpTokenResponse {
  revoked: boolean;
}

/** Backend ``TokenCreated``: a flat ``TokenOut`` plus the one-time plaintext. */
type TokenCreatedWire = MemoryMcpToken & { token: string };

function toCreated(raw: TokenCreatedWire): MemoryMcpTokenCreated {
  const { token, ...row } = raw;
  return { token: row, plaintext: token };
}

export const memoryMcpApi = {
  list: () => request<MemoryMcpToken[]>("/memory-mcp/tokens"),

  create: (body: CreateMemoryMcpTokenBody) =>
    request<TokenCreatedWire>("/memory-mcp/tokens", {
      method: "POST",
      body: JSON.stringify(body),
    }).then(toCreated),

  revoke: (tokenId: string) =>
    request<RevokeMemoryMcpTokenResponse>(
      `/memory-mcp/tokens/${encodeURIComponent(tokenId)}`,
      { method: "DELETE" },
    ),
};

export default memoryMcpApi;
