/**
 * Typed client for the expert-team run surface (T-20, contract = T-16's routes).
 *
 * **Contract source of truth**: `src/octop/api/routers/team_runs.py` — the
 * `response_model` of each route, not `PLAN.md`. Where PLAN and the implementation
 * disagree, the implementation wins and the drift is reported (see the T-20
 * delivery note). Types below mirror the Pydantic models one-to-one, including the
 * two "not measured yet" shapes:
 *
 * * `MetricSectionOut.state` — `measured | proxy | empty | partial` (PLAN AM-26):
 *   an `empty` section has **no event family yet**, so the UI must say so instead of
 *   rendering a measured `0` ("沉默会被读成'没有卡点'").
 * * `ArtifactItemOut.phase/version/hash/created_at` — the index columns exist but
 *   **no writer materialises `kind='workflow'` rows until T-45**, so these are
 *   `null` today; the UI shows "待写入方" for the null case rather than a fake value.
 *
 * `AGENTS.md` §5: this module is the only place that talks HTTP for runs — pages
 * and components receive data as props.
 */

import { request } from "../request";

export type RunStatus =
  | "running"
  | "awaiting_confirmation"
  | "awaiting_decision"
  | "complete"
  | "failed"
  | "cancelled";

export type TaskStorageStatus =
  | "planning"
  | "todo"
  | "doing"
  | "review"
  | "blocked"
  | "done"
  | "cancelled";

/** Which slice of the run a `state` request asked for (progressive loading). */
export type RunStateSection =
  | "summary"
  | "people"
  | "feed"
  | "artifacts"
  | "tasks"
  | "check";

/** What a metric section's number is worth (PLAN AM-26). */
export type MetricSectionState = "measured" | "proxy" | "empty" | "partial";

export interface PhaseWire {
  phase: string;
  seq: number;
  status: "pending" | "active" | "passed" | "failed" | "skipped";
  /** Carries `skipped_roles` when the tier cap cut members (AM-1 ④). */
  gate_detail: Record<string, unknown>;
  entered_at: number | null;
  passed_at: number | null;
}

export interface MemberWire {
  role: string;
  agent_id: string;
  is_lead: boolean;
}

export interface RunSummaryWire {
  run_id: string;
  project_id: string;
  team_agent_id: string;
  goal: string;
  mode: string;
  deliverable: string;
  tier: string;
  status: RunStatus;
  phase: string;
  room_thread_id: string | null;
  max_review_rounds: number;
  created_at: number;
  updated_at: number;
}

export interface RunDetailWire extends RunSummaryWire {
  phases: PhaseWire[];
  members: MemberWire[];
  allowed_phases: string[];
  pending_decision: Record<string, unknown> | null;
}

export interface TaskNodeWire {
  id: string;
  title: string;
  kind: string;
  owner: string;
  status: TaskStorageStatus;
  phase: string | null;
  round: number;
  attempt: number;
  attemptId: string | null;
  verdict: string | null;
  acceptance: string[];
  inScope: string[];
  verify: string[];
  dependsOn: string[];
  changedPaths: string[];
}

export interface TaskEdgeWire {
  from: string;
  to: string;
}

export interface ViolationWire {
  code: string;
  detail: string;
  task_id: string | null;
}

export interface TaskBoardWire {
  nodes: TaskNodeWire[];
  edges: TaskEdgeWire[];
  violations: ViolationWire[];
}

/** Index fields are `null` until a writer materialises them (T-45). */
export interface ArtifactItemWire {
  name: string;
  present: boolean;
  owners: string[] | null;
  revision: string | null;
  owner_role: string | null;
  phase: string | null;
  version: number | null;
  hash: string | null;
  created_at: number | null;
}

export interface CheckWire {
  violations: string[];
  finding_reopened: Record<string, unknown> | null;
}

export interface FeedEntryWire {
  action: string;
  actor: string;
  at: number;
  task_id: string | null;
  payload: Record<string, unknown>;
}

/**
 * The decision payload's two lifecycle values — **taken from the backend writer**, not
 * guessed: `raise_decision` writes `status: "pending"` (`run_service.py:1165`) and
 * `decide()` **writes the payload back** with `status: "resolved"` (`:1223`) rather than
 * clearing it. ⇒ `pending_decision` never returns to `null` once raised, so
 * **"is a human still needed?" must be read from `status`**, never from presence.
 */
export type DecisionStatus = "pending" | "resolved";

/** One pending/resolved decision payload (`RunDetailOut.pending_decision`). */
export interface DecisionPayload {
  decision_id?: string;
  status?: DecisionStatus | string;
  kind?: string | null;
  options?: string[];
  question?: string;
  choice?: string | null;
  note?: string | null;
  resolved_at?: number | null;
  [key: string]: unknown;
}

/**
 * **The single predicate** for "a decision is still waiting on a human".
 *
 * Presence is not the question: after `decide()` the payload stays on the run marked
 * `resolved`. Anything that renders a confirm affordance, a gate red bar or a parked
 * phase must filter through this function — otherwise the UI claims the run is still
 * blocked long after it moved on.
 */
export function isDecisionPending(
  decision: DecisionPayload | Record<string, unknown> | null | undefined,
): decision is Record<string, unknown> {
  return decision?.status === "pending";
}

export interface RunStateWire {
  section: string;
  run: RunSummaryWire;
  phases: PhaseWire[];
  members: MemberWire[];
  tasks: TaskNodeWire[];
  artifacts: ArtifactItemWire[];
  feed: FeedEntryWire[];
  check: CheckWire | null;
}

export interface MetricSectionWire {
  title: string;
  lines: string[];
  state: MetricSectionState;
  note: string;
}

export interface MetricsWire {
  sections: MetricSectionWire[];
  rendered: string;
}

export interface ExportWire {
  name: string;
  content: string;
  files: string[];
}

export interface DecisionWire {
  decision_id: string;
  status: string;
  choice: string | null;
  kind: string | null;
}

export interface DispatchWire {
  task_id: string;
  channel: string;
  thread_id: string | null;
}

/** The four read-only projections `GET /export/{name}` can serve. */
export const EXPORT_NAMES = [
  "TASKS.json",
  "任务看板.md",
  "STATE.json",
  "ROSTER.json",
] as const;
export type ExportName = (typeof EXPORT_NAMES)[number];

// ------------------------------------------------------------------ read paths

export function listRuns(): Promise<RunSummaryWire[]> {
  return request<RunSummaryWire[]>("/team/runs");
}

export function getRun(runId: string): Promise<RunDetailWire> {
  return request<RunDetailWire>(`/team/runs/${encodeURIComponent(runId)}`);
}

/** Progressive load: ask for one section; the other fields come back empty. */
export function getRunState(
  runId: string,
  section: RunStateSection,
): Promise<RunStateWire> {
  return request<RunStateWire>(
    `/team/runs/${encodeURIComponent(runId)}/state?section=${encodeURIComponent(
      section,
    )}`,
  );
}

export function listTasks(runId: string): Promise<TaskBoardWire> {
  return request<TaskBoardWire>(
    `/team/runs/${encodeURIComponent(runId)}/tasks`,
  );
}

export function getMetrics(runId: string): Promise<MetricsWire> {
  return request<MetricsWire>(
    `/team/runs/${encodeURIComponent(runId)}/metrics`,
  );
}

export function checkRun(runId: string): Promise<CheckWire> {
  return request<CheckWire>(`/team/runs/${encodeURIComponent(runId)}/check`);
}

export function listArtifacts(
  runId: string,
): Promise<{ items: ArtifactItemWire[] }> {
  return request<{ items: ArtifactItemWire[] }>(
    `/team/runs/${encodeURIComponent(runId)}/artifacts`,
  );
}

export function getArtifact(
  runId: string,
  name: string,
): Promise<ArtifactItemWire & { content: string }> {
  return request<ArtifactItemWire & { content: string }>(
    `/team/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(
      name,
    )}`,
  );
}

export function getExport(
  runId: string,
  name: ExportName,
): Promise<ExportWire> {
  return request<ExportWire>(
    `/team/runs/${encodeURIComponent(runId)}/export/${encodeURIComponent(
      name,
    )}`,
  );
}

// ----------------------------------------------------------------- write paths

export interface RunCreateBody {
  team_agent_id: string;
  goal: string;
  mode?: "one-shot" | "persist";
  deliverable?: string;
  tier?: "quick" | "standard" | "strict" | null;
  roles?: string[] | null;
  host_agent_id?: string | null;
  run_root?: string | null;
  max_review_rounds?: number;
}

export interface TaskCreateBody {
  title: string;
  kind?: string;
  owner?: string;
  spec?: string;
  acceptance?: string[];
  inScope?: string[];
  verify?: string[];
  dependsOn?: string[];
  phase?: string | null;
  round?: number | null;
}

export type TaskOp =
  | "claim"
  | "start"
  | "report"
  | "complete"
  | "fail"
  | "rework";

export interface TaskPatchBody {
  attemptId: string;
  op: TaskOp;
  status?: string | null;
  verdict?: "pass" | "needs_revision" | "reject" | null;
  findings?: {
    title: string;
    severity: "low" | "medium" | "high" | "blocker";
    detail?: string;
    round?: number | null;
  }[];
  changedPaths?: string[];
  role?: string;
  round?: number | null;
}

export function createRun(body: RunCreateBody): Promise<RunDetailWire> {
  return request<RunDetailWire>("/team/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function createTask(
  runId: string,
  body: TaskCreateBody,
): Promise<TaskNodeWire> {
  return request<TaskNodeWire>(
    `/team/runs/${encodeURIComponent(runId)}/tasks`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function patchTask(
  runId: string,
  taskId: string,
  body: TaskPatchBody,
): Promise<TaskNodeWire> {
  return request<TaskNodeWire>(
    `/team/runs/${encodeURIComponent(runId)}/tasks/${encodeURIComponent(
      taskId,
    )}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

/** Ownership + revision CAS are enforced server-side; a refusal leaves the file intact. */
export function putArtifact(
  runId: string,
  name: string,
  body: { content: string; revision?: string; role: string },
): Promise<{ name: string; revision: string; hash: string }> {
  return request<{ name: string; revision: string; hash: string }>(
    `/team/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(
      name,
    )}`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

export function advanceRun(
  runId: string,
  toPhase: string,
  note?: string,
): Promise<RunDetailWire> {
  return request<RunDetailWire>(
    `/team/runs/${encodeURIComponent(runId)}:advance`,
    {
      method: "POST",
      body: JSON.stringify({ to_phase: toPhase, note }),
    },
  );
}

export function decideRun(
  runId: string,
  body: { decision_id: string; choice: string; note?: string },
): Promise<DecisionWire> {
  return request<DecisionWire>(
    `/team/runs/${encodeURIComponent(runId)}/decision`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function resumeRun(runId: string): Promise<RunSummaryWire> {
  return request<RunSummaryWire>(
    `/team/runs/${encodeURIComponent(runId)}:resume`,
    {
      method: "POST",
    },
  );
}

export function cancelRun(runId: string): Promise<RunSummaryWire> {
  return request<RunSummaryWire>(
    `/team/runs/${encodeURIComponent(runId)}:cancel`,
    {
      method: "POST",
    },
  );
}

export function dispatchTask(
  runId: string,
  taskId: string,
): Promise<DispatchWire> {
  return request<DispatchWire>(
    `/team/runs/${encodeURIComponent(runId)}/tasks/${encodeURIComponent(
      taskId,
    )}:dispatch`,
    { method: "POST" },
  );
}

/** Storage statuses the UI cares about when counting "in flight" work. */
export const IN_FLIGHT_STATUSES: readonly TaskStorageStatus[] = [
  "planning",
  "todo",
  "doing",
  "review",
];
