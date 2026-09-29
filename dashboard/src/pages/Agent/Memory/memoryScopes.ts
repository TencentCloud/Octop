/**
 * Typed client for ``GET /agents/{agent_id}/memory/scopes`` (T-37 / T-38).
 *
 * T-38 is the read-only "scope" visibility layer: the switcher changes
 * ``project_id`` / ``team_id``, and the backend answers with the agent's memory
 * grouped per namespace layer (``project`` → ``team`` → ``agent``), already
 * deduped in that order (plan R17). A row that appears under ``agent`` is
 * therefore one that is **not yet** in the team or project layer — that is the
 * R19 fact the panel annotates.
 *
 * NOTE (T-38 write scope): the canonical home for a per-agent memory wrapper is
 * ``api/modules/memoryDashboard.ts`` (its docstring already claims
 * ``/agents/{aid}/memory/*``). This task's write scope covered
 * ``pages/Agent/Memory`` only, so the wrapper lives beside its single consumer.
 * Moving it is a copy-paste; the wire types below are the contract either way.
 *
 * Read-only by construction: this module exposes exactly one GET and no write
 * verb (SPEC B38 — read visibility must not become write access).
 */

import { request } from "../../../api/request";

/** The three isolation axes, in the backend's dedup order (highest first). */
export type MemorySourceLayer = "project" | "team" | "agent";

export interface MemoryScopeItem {
  id: string;
  text: string;
  source_layer: MemorySourceLayer;
  namespace: string;
  created_at: string | null;
  importance: string | null;
  entity_id: string | null;
  /** Set for rows read from the project layer. */
  project_id: string | null;
}

export interface MemoryScopeGroup {
  source_layer: MemorySourceLayer;
  namespace: string;
  total: number;
  items: MemoryScopeItem[];
}

export interface MemoryScopesResponse {
  agent_id: string;
  groups: MemoryScopeGroup[];
}

export interface MemoryScopesQuery {
  /** Supplying this asks for the project layer; requires PROJECT_READ (403 otherwise). */
  projectId?: string | null;
  /** Team host agent id; omitted when the agent belongs to no team. */
  teamId?: string | null;
  limit?: number;
}

export async function fetchMemoryScopes(
  agentId: string,
  query: MemoryScopesQuery = {},
): Promise<MemoryScopesResponse> {
  const params = new URLSearchParams();
  if (query.projectId) params.set("project_id", query.projectId);
  if (query.teamId) params.set("team_id", query.teamId);
  if (query.limit) params.set("limit", String(query.limit));
  const qs = params.toString();
  return request<MemoryScopesResponse>(
    `/agents/${encodeURIComponent(agentId)}/memory/scopes${qs ? `?${qs}` : ""}`,
  );
}

/**
 * ``true`` when the error is an HTTP 403 from the project gate.
 *
 * Switching to a project the caller cannot read is a **permission state**, not a
 * failure: the panel must render "no access" instead of letting it bubble up as
 * a page crash. ``request`` throws ``Error`` whose message carries the response
 * body, so the status is recovered the same way ``parseApiError`` reads codes.
 */
export function isPermissionDenied(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const raw = error.message;
  if (/\b403\b/.test(raw)) return true;
  return (
    raw.includes("PROJECT_FORBIDDEN") ||
    raw.includes("PERMISSION_DENIED") ||
    raw.includes("FORBIDDEN")
  );
}
