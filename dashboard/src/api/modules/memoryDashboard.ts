/**
 * memoryDashboard — talks to the per-agent harness-memory dashboard
 * surface mounted at ``/api/agents/{aid}/memory/*`` (octop router).
 *
 * Each function maps one-to-one to a backend endpoint. Type defs
 * mirror the wire shape the harness-memory bridge handlers emit
 * (see ``harness_memory.application.dashboard_data``); we deliberately
 * keep the shapes loose / partial and rely on the BE to never break
 * field names, so this client doesn't need to round-trip every CI run.
 */

import { request } from "../request";

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

export type AtomKind =
  | "Fact"
  | "Decision"
  | "Task"
  | "Preference"
  | "ConflictCandidate";

export type Importance = "low" | "medium" | "high";
export type Confidence = "low" | "medium" | "high";

export interface AtomItem {
  id: string;
  entity_id: string;
  candidate_id: string;
  assertion: string;
  verbatim_quote: string;
  search_terms?: string[];
  occurred_at?: string | null;
  importance: Importance;
  confidence: Confidence;
  /**
   * Backend AtomCard has no status field. Deprecation is represented by deprecated_at:
   * null = active; timestamp = deprecated by a newer atom or manual action.
   * Use isAtomDeprecated() instead of comparing against the removed status field.
   */
  deprecated_at?: string | null;
  superseded_by?: string | null;
  created_at: string;
  /** Filled by the dashboard handler from the linked Candidate. */
  kind: AtomKind | null;
}

/** Whether an atom is deprecated. Active atoms have deprecated_at = null. */
export function isAtomDeprecated(
  atom: Pick<AtomItem, "deprecated_at">,
): boolean {
  return atom.deprecated_at != null;
}

export interface ListAtomsResponse {
  items: AtomItem[];
  total: number;
  has_more: boolean;
}

export interface RawEventItem {
  id: string;
  host: string;
  session_id: string | null;
  thread_id: string | null;
  user: string | null;
  timestamp: string;
  event_type: string;
  content: string;
  payload?: Record<string, unknown>;
}

export interface ListRawEventsResponse {
  items: RawEventItem[];
  total: number;
  has_more: boolean;
}

export interface ListRawEventsBody {
  session_id?: string;
  thread_id?: string;
  event_type?: string;
  query?: string;
  offset?: number;
  limit?: number;
}

export type ExtractTriggerMode = "idle" | "interval";

export interface ExtractConfig {
  /** Missing on older Octop API processes; absence keeps the historical enabled default. */
  memory_enabled?: boolean;
  extract_on_session_end: boolean;
  extract_trigger_mode: ExtractTriggerMode;
  extract_idle_seconds: number;
  extract_interval_seconds: number;
  /**
   * "provider/model" ref used for extraction / promotion. null/absent = AUTO
   * (follow the chat model); send "" to reset back to AUTO.
   */
  aux_model?: string | null;
}

export interface EntityItem {
  id: string;
  entity_type: string;
  canonical_name: string;
  aliases: string[];
  atom_count: number;
  created_at: string;
  page_dirty?: boolean;
}

/** L3 entity page — the long-form, LLM-regenerated summary for a topic. */
export interface EntityPage {
  id: string;
  entity_id: string;
  summary_markdown: string;
  headline: string;
  topics: string[];
  dirty: boolean;
  summary_version: number;
  created_at: string;
  updated_at: string;
}

export type EntityDetail = EntityItem & { page: EntityPage | null };

export interface ListEntitiesResponse {
  items: EntityItem[];
  total: number;
  has_more: boolean;
}

export interface EpisodeItem {
  id: string;
  occurred_at: string;
  summary: string;
  verbatim_quote: string;
  emotion: string;
  intensity: number;
  people: string[];
  topics: string[];
  created_at: string;
}

export interface ListEpisodesResponse {
  items: EpisodeItem[];
  total: number;
  has_more: boolean;
}

/** Structured run stats attached to an ``extract_run`` journal entry. */
export interface ExtractRunStats {
  events_considered?: number;
  events_extracted?: number;
  candidates?: number;
  promoted?: number;
  merged?: number;
  conflicts?: number;
  needs_review?: number;
  dropped?: number;
  llm_calls?: number;
  failure_reason?: string | null;
}

export interface JournalItem {
  id: string;
  timestamp: string;
  action: string;
  actor: string;
  target_entity_id?: string | null;
  target_atom_id?: string | null;
  target_candidate_id?: string | null;
  note?: string | null;
  /** Short target memory/topic text enriched by the backend for specific action display. */
  target_summary?: string | null;
  /** Present on ``extract_run`` rows: structured stats for this extraction pass. */
  after?: ExtractRunStats | null;
}

export interface ListJournalResponse {
  items: JournalItem[];
  total: number;
  has_more: boolean;
}

export type CandidateStatus =
  | "pending"
  | "needs_review"
  | "conflict"
  | "promoted"
  | "rejected";

export interface CandidateItem {
  id: string;
  raw_event_ids: string[];
  candidate_type: AtomKind;
  status: CandidateStatus;
  title: string;
  assertion: string;
  verbatim_quote: string;
  quote_event_id: string;
  subject_name: string;
  subject_entity_type: string;
  target_entity_id: string | null;
  confidence: Confidence;
  importance: Importance;
  recommended_action: string;
  promotion_reason: string;
  extractor_version: string;
  created_at: string;
  decided_at?: string | null;
  decided_by?: string | null;
  session_id?: string | null;
}

export interface ListCandidatesResponse {
  items: CandidateItem[];
  total: number;
  has_more: boolean;
}

export interface PromoteCandidateResponse {
  promoted: number;
  merged: number;
  conflicts: number;
  needs_review: number;
  dropped: number;
  llm_calls: number;
}

export interface RejectCandidateResponse {
  candidate_id: string;
  status: "rejected";
}

export interface StatsCounts {
  raw_events: number;
  atoms: number;
  entities: number;
  dirty_pages: number;
  episodes: number;
  candidates_pending: number;
  atoms_delta_7d: number;
  entities_delta_7d: number;
  episodes_delta_7d: number;
}

export interface StatsAtomKindsResponse {
  series: Array<{ kind: string; count: number }>;
}

export interface StatsGrowthBucket {
  date: string; // YYYY-MM-DD
  atoms: number;
  entities: number;
  episodes: number;
}

export interface StatsGrowthResponse {
  series: StatsGrowthBucket[];
}

export interface RecentJournalResponse {
  items: JournalItem[];
}

export interface TerminalAtomResponse {
  items: AtomItem[];
}

export interface TerminalEpisodeResponse {
  items: EpisodeItem[];
}

export interface TerminalEntityResponse {
  items: EntityItem[];
}

// ---------------------------------------------------------------------------
// Request bodies
// ---------------------------------------------------------------------------

export interface ListAtomsBody {
  entity_id?: string;
  candidate_type?: AtomKind;
  importance_min?: Importance;
  include_deprecated?: boolean;
  query?: string;
  order_by?: "created_at" | "occurred_at" | "importance";
  order?: "asc" | "desc";
  offset?: number;
  limit?: number;
}

export interface ListEntitiesBody {
  entity_type?: string;
  query?: string;
  order_by?: "created_at" | "atom_count";
  order?: "asc" | "desc";
  offset?: number;
  limit?: number;
}

export interface ListEpisodesBody {
  emotion?: string;
  intensity_min?: number;
  date_from?: string;
  date_to?: string;
  topic?: string;
  query?: string;
  offset?: number;
  limit?: number;
}

export interface ListJournalBody {
  action?: string;
  target_type?: "atom" | "entity" | "candidate";
  actor?: string;
  time_from?: string;
  time_to?: string;
  target_entity_id?: string;
  target_atom_id?: string;
  target_candidate_id?: string;
  offset?: number;
  limit?: number;
}

export interface ListCandidatesBody {
  status?: CandidateStatus;
  candidate_type?: AtomKind;
  session_id?: string;
  target_entity_id?: string;
  time_from?: string;
  time_to?: string;
  query?: string;
  offset?: number;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

const base = (aid: string) => `/agents/${aid}/memory`;

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });

export const memoryDashboardApi = {
  // listings
  listAtoms: (aid: string, body?: ListAtomsBody) =>
    post<ListAtomsResponse>(`${base(aid)}/atoms/list`, body),

  listEntities: (aid: string, body?: ListEntitiesBody) =>
    post<ListEntitiesResponse>(`${base(aid)}/entities/list`, body),

  listEpisodes: (aid: string, body?: ListEpisodesBody) =>
    post<ListEpisodesResponse>(`${base(aid)}/episodes/list`, body),

  listJournal: (aid: string, body?: ListJournalBody) =>
    post<ListJournalResponse>(`${base(aid)}/journal/list`, body),

  listCandidates: (aid: string, body?: ListCandidatesBody) =>
    post<ListCandidatesResponse>(`${base(aid)}/candidates/list`, body),

  listRawEvents: (aid: string, body?: ListRawEventsBody) =>
    post<ListRawEventsResponse>(`${base(aid)}/raw_events/list`, body),

  // single fetches
  getAtom: (aid: string, atomId: string) =>
    request<AtomItem>(`${base(aid)}/atoms/${encodeURIComponent(atomId)}`),

  getEntity: (aid: string, entityId: string) =>
    request<EntityDetail>(
      `${base(aid)}/entities/${encodeURIComponent(entityId)}`,
    ),

  getEpisode: (aid: string, episodeId: string) =>
    request<EpisodeItem>(
      `${base(aid)}/episodes/${encodeURIComponent(episodeId)}`,
    ),

  getRawEvent: (aid: string, eventId: string) =>
    request<unknown>(`${base(aid)}/raw_events/${encodeURIComponent(eventId)}`),

  getCandidate: (aid: string, candidateId: string) =>
    request<unknown>(
      `${base(aid)}/candidates/${encodeURIComponent(candidateId)}`,
    ),

  // stats / overview
  statsCounts: (aid: string) =>
    request<StatsCounts>(`${base(aid)}/stats/counts`),

  statsGrowth: (aid: string, days = 7) =>
    request<StatsGrowthResponse>(`${base(aid)}/stats/growth?days=${days}`),

  statsAtomKinds: (aid: string) =>
    request<StatsAtomKindsResponse>(`${base(aid)}/stats/atom_kinds`),

  recentJournal: (aid: string, limit = 5) =>
    request<RecentJournalResponse>(
      `${base(aid)}/journal/recent?limit=${limit}`,
    ),

  // write actions
  promoteCandidate: (aid: string, candidateId: string) =>
    request<PromoteCandidateResponse>(
      `${base(aid)}/candidates/${encodeURIComponent(candidateId)}:promote`,
      { method: "POST" },
    ),

  rejectCandidate: (
    aid: string,
    candidateId: string,
    body?: { reason?: string; actor?: string },
  ) =>
    request<RejectCandidateResponse>(
      `${base(aid)}/candidates/${encodeURIComponent(candidateId)}:reject`,
      { method: "POST", body: JSON.stringify(body ?? {}) },
    ),

  deprecateAtom: (
    aid: string,
    atomId: string,
    body?: { reason?: string; actor?: string },
  ) =>
    request<unknown>(
      `${base(aid)}/atoms/${encodeURIComponent(atomId)}:deprecate`,
      { method: "POST", body: JSON.stringify(body ?? {}) },
    ),

  // terminal aggregator (5 cards)
  terminalAboutMe: (aid: string, limit = 5) =>
    request<TerminalAtomResponse>(
      `${base(aid)}/terminal/about_me?limit=${limit}`,
    ),

  terminalCurrentFocus: (aid: string, limit = 5) =>
    request<TerminalAtomResponse>(
      `${base(aid)}/terminal/current_focus?limit=${limit}`,
    ),

  terminalThingsYouToldMe: (aid: string, limit = 5) =>
    request<TerminalAtomResponse>(
      `${base(aid)}/terminal/things_you_told_me?limit=${limit}`,
    ),

  terminalRecentStories: (aid: string, limit = 5) =>
    request<TerminalEpisodeResponse>(
      `${base(aid)}/terminal/recent_stories?limit=${limit}`,
    ),

  terminalEntities: (aid: string, limit = 5) =>
    request<TerminalEntityResponse>(
      `${base(aid)}/terminal/entities?limit=${limit}`,
    ),

  // extraction-trigger config
  getExtractConfig: (aid: string) =>
    request<ExtractConfig>(`${base(aid)}/extract-config`),

  putExtractConfig: (aid: string, body: Partial<ExtractConfig>) =>
    request<ExtractConfig>(`${base(aid)}/extract-config`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};

export default memoryDashboardApi;
