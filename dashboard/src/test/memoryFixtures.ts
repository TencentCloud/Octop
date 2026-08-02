/**
 * Memory test fixtures + helpers.
 *
 * Centralized sample data so the 6 Memory component tests share a
 * consistent shape and any wire-format change ripples through one
 * file instead of six.
 */

import type {
  AtomItem,
  CandidateItem,
  EntityItem,
  EpisodeItem,
  JournalItem,
  StatsAtomKindsResponse,
  StatsCounts,
  StatsGrowthResponse,
  RecentJournalResponse,
  ListAtomsResponse,
  ListEntitiesResponse,
  ListEpisodesResponse,
  ListJournalResponse,
  ListCandidatesResponse,
  TerminalAtomResponse,
  TerminalEntityResponse,
  TerminalEpisodeResponse,
  PromoteCandidateResponse,
  RejectCandidateResponse,
} from "../api/modules/memoryDashboard";

// ---------------------------------------------------------------------------
// Factories
// ---------------------------------------------------------------------------

export function makeAtom(overrides: Partial<AtomItem> = {}): AtomItem {
  return {
    id: "atom-1",
    entity_id: "ent-1",
    candidate_id: "cand-1",
    assertion: "用户喜欢喝美式咖啡。",
    verbatim_quote: "我喜欢喝美式咖啡",
    search_terms: ["coffee", "美式"],
    occurred_at: null,
    importance: "medium",
    confidence: "high",
    deprecated_at: null,
    created_at: "2026-06-29T10:00:00Z",
    kind: "Preference",
    ...overrides,
  };
}

export function makeEntity(overrides: Partial<EntityItem> = {}): EntityItem {
  return {
    id: "ent-1",
    entity_type: "Person",
    canonical_name: "用户",
    aliases: ["You", "you"],
    atom_count: 4,
    created_at: "2026-06-20T08:00:00Z",
    ...overrides,
  };
}

export function makeEpisode(overrides: Partial<EpisodeItem> = {}): EpisodeItem {
  return {
    id: "ep-1",
    occurred_at: "2026-06-28T22:00:00Z",
    summary: "用户分享了关于咖啡偏好的故事。",
    verbatim_quote: "上周末我去了那家新开的咖啡店",
    emotion: "happy",
    intensity: 3,
    people: ["user"],
    topics: ["coffee", "weekend"],
    created_at: "2026-06-28T22:05:00Z",
    ...overrides,
  };
}

export function makeJournal(overrides: Partial<JournalItem> = {}): JournalItem {
  return {
    id: "j-1",
    timestamp: "2026-06-29T10:00:00Z",
    action: "promote",
    actor: "user",
    target_atom_id: "atom-1",
    target_entity_id: null,
    target_candidate_id: null,
    note: "Promoted via dashboard.",
    ...overrides,
  };
}

export function makeCandidate(
  overrides: Partial<CandidateItem> = {},
): CandidateItem {
  return {
    id: "cand-1",
    raw_event_ids: ["raw-1"],
    candidate_type: "Preference",
    status: "pending",
    title: "咖啡偏好",
    assertion: "用户喜欢喝美式咖啡。",
    verbatim_quote: "我喜欢喝美式咖啡",
    quote_event_id: "raw-1",
    subject_name: "用户",
    subject_entity_type: "User",
    target_entity_id: null,
    confidence: "high",
    importance: "medium",
    recommended_action: "create_new",
    promotion_reason: "stable preference",
    extractor_version: "v1.0",
    created_at: "2026-06-29T09:00:00Z",
    decided_at: null,
    decided_by: null,
    session_id: "sess-1",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Wrapped responses (matches what client returns)
// ---------------------------------------------------------------------------

export function listAtomsResp(items: AtomItem[]): ListAtomsResponse {
  return { items, total: items.length, has_more: false };
}
export function listEntitiesResp(items: EntityItem[]): ListEntitiesResponse {
  return { items, total: items.length, has_more: false };
}
export function listEpisodesResp(items: EpisodeItem[]): ListEpisodesResponse {
  return { items, total: items.length, has_more: false };
}
export function listJournalResp(items: JournalItem[]): ListJournalResponse {
  return { items, total: items.length, has_more: false };
}
export function listCandidatesResp(
  items: CandidateItem[],
): ListCandidatesResponse {
  return { items, total: items.length, has_more: false };
}
export function terminalAtomResp(items: AtomItem[]): TerminalAtomResponse {
  return { items };
}
export function terminalEntityResp(
  items: EntityItem[],
): TerminalEntityResponse {
  return { items };
}
export function terminalEpisodeResp(
  items: EpisodeItem[],
): TerminalEpisodeResponse {
  return { items };
}
export function recentJournalResp(items: JournalItem[]): RecentJournalResponse {
  return { items };
}
export function statsCountsFixture(
  overrides: Partial<StatsCounts> = {},
): StatsCounts {
  return {
    raw_events: 45,
    atoms: 5,
    entities: 3,
    dirty_pages: 0,
    episodes: 2,
    candidates_pending: 1,
    atoms_delta_7d: 3,
    entities_delta_7d: 1,
    episodes_delta_7d: 2,
    ...overrides,
  };
}
export function statsAtomKindsFixture(): StatsAtomKindsResponse {
  return {
    series: [
      { kind: "Preference", count: 2 },
      { kind: "Fact", count: 1 },
      { kind: "Decision", count: 1 },
      { kind: "Task", count: 1 },
    ],
  };
}
export function statsGrowthFixture(): StatsGrowthResponse {
  return {
    series: [
      { date: "2026-06-23", atoms: 0, entities: 0, episodes: 0, turns: 1 },
      { date: "2026-06-24", atoms: 1, entities: 0, episodes: 0, turns: 2 },
      { date: "2026-06-25", atoms: 1, entities: 1, episodes: 0, turns: 3 },
      { date: "2026-06-26", atoms: 1, entities: 0, episodes: 1, turns: 1 },
      { date: "2026-06-27", atoms: 0, entities: 0, episodes: 0, turns: 0 },
      { date: "2026-06-28", atoms: 0, entities: 0, episodes: 1, turns: 4 },
      { date: "2026-06-29", atoms: 2, entities: 1, episodes: 0, turns: 2 },
    ],
  };
}

export function promoteResp(): PromoteCandidateResponse {
  return {
    promoted: 1,
    merged: 0,
    conflicts: 0,
    needs_review: 0,
    dropped: 0,
    llm_calls: 1,
  };
}

export function rejectResp(): RejectCandidateResponse {
  return { candidate_id: "cand-1", status: "rejected" };
}
