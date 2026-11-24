/**
 * memoryMcp — user-level API tokens for the memory MCP server.
 *
 * Routes live under ``/api/memory-mcp/tokens`` (``octop.api.routers.memory_mcp``).
 * Each token is bound to a memory space. The plaintext is available when the
 * token is created or rotated, and only the digest is stored server-side.
 *
 * Wire shapes are snake_case on purpose, mirroring the backend ``TokenOut`` /
 * ``TokenCreated`` models.
 */

import { request } from "../request";

/**
 * Usage of one client integration, keyed in ``MemoryMcpToken.client_stats`` by
 * the ``X-Octop-Client`` value the client sends (e.g. ``claude-code``).
 */
export interface MemoryMcpClientStat {
  /** ISO-8601 UTC of the first request carrying this client header. */
  first_seen: string;
  /** ISO-8601 UTC of the most recent such request. */
  last_seen: string;
  /** Requests seen with this client header. */
  count: number;
}

export interface MemoryMcpToken {
  /** Public id used to revoke the token. */
  token_id: string;
  /** Client name supplied at creation, e.g. ``codex@macbook``. */
  name: string;
  /** Octop experts associated with the token's space, when available. */
  expert_ids: string[] | null;
  space_id?: string;
  scopes?: string[];
  /** Masked value safe to display, e.g. ``omcp_…abcd``. */
  token_hint: string;
  /** ISO-8601 UTC. */
  created_at: string;
  /** ISO-8601 UTC, or null when the token has never been used. */
  last_used_at: string | null;
  /** MCP endpoint this token talks to (standalone octop-memory service). */
  mcp_url?: string;
  /** ISO-8601 UTC once revoked; null while the token is active. */
  revoked_at: string | null;
  /**
   * Clients switched off for this token; null means every client may call.
   * A disabled client is rejected server-side regardless of ``client_stats``.
   */
  disabled_clients: string[] | null;
  /**
   * Per-client usage, or null until some client sends ``X-Octop-Client``.
   * Requests without that header are counted only in ``last_used_at``.
   */
  client_stats: Record<string, MemoryMcpClientStat> | null;
}

/** Successful create result: the token row plus its one-time plaintext. */
export interface MemoryMcpTokenCreated {
  token: MemoryMcpToken;
  plaintext: string;
}

export interface CreateMemoryMcpTokenBody {
  name: string;
  /** The selected expert identifies its default or explicitly bound space. */
  expert_ids?: string[] | null;
  space_id?: string;
  scopes?: ("read" | "write")[];
}

/**
 * Partial update body for ``PATCH /memory-mcp/tokens/{token_id}``.
 */
export interface UpdateMemoryMcpTokenBody {
  /** New display name; omitted leaves it untouched. */
  name?: string;
  /** Exactly one id selects the expert for the legacy workflow. */
  expert_ids?: string[] | null;
  /** Clients switched off; an empty list is sent as null ("all allowed"). */
  disabled_clients?: string[] | null;
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
  getCodexModel: (tokenId: string, space: string) =>
    request<{ model: string | null }>(
      `/memory-mcp/tokens/${encodeURIComponent(
        tokenId,
      )}/codex-model?${new URLSearchParams({ space_id: space })}`,
    ),
  setCodexModel: (tokenId: string, space: string, model: string | null) =>
    request<{ model: string | null }>(
      `/memory-mcp/tokens/${encodeURIComponent(
        tokenId,
      )}/codex-model?${new URLSearchParams({ space_id: space })}`,
      { method: "PUT", body: JSON.stringify({ model }) },
    ),
  list: (spaceId?: string) =>
    request<MemoryMcpToken[]>(
      spaceId
        ? `/memory-mcp/tokens?${new URLSearchParams({ space_id: spaceId })}`
        : "/memory-mcp/tokens",
    ),

  create: (body: CreateMemoryMcpTokenBody) =>
    request<TokenCreatedWire>("/memory-mcp/tokens", {
      method: "POST",
      body: JSON.stringify(body),
    }).then(toCreated),

  /** Rename and/or re-bind the token's expert. Returns ``TokenOut`` (no plaintext). */
  update: (tokenId: string, body: UpdateMemoryMcpTokenBody) =>
    request<MemoryMcpToken>(
      `/memory-mcp/tokens/${encodeURIComponent(tokenId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    ),

  revoke: (tokenId: string) =>
    request<RevokeMemoryMcpTokenResponse>(
      `/memory-mcp/tokens/${encodeURIComponent(tokenId)}`,
      { method: "DELETE" },
    ),

  /**
   * Issue a fresh secret for an existing token; the old plaintext stops working
   * immediately. Returns ``TokenOut`` plus the one-time plaintext, exactly like
   * ``create``. Revoked tokens are rejected by the server (409).
   */
  rotate: (tokenId: string, spaceId?: string) =>
    request<TokenCreatedWire>(
      `/memory-mcp/tokens/${encodeURIComponent(tokenId)}/rotate${
        spaceId ? `?${new URLSearchParams({ space_id: spaceId })}` : ""
      }`,
      { method: "POST" },
    ).then(toCreated),
};

export default memoryMcpApi;
