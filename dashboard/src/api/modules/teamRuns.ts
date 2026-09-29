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

/**
 * A draft task row. Its field set is owned by the backend (`PlanDraft.tasks` is
 * `list[dict[str, Any]]`, validated by `normalize_draft`), so an edit must copy the row
 * and patch it in place — unknown keys survive the round trip instead of being rebuilt.
 */
export interface PlanTaskDraft {
  id: string;
  owner: string;
  title: string;
  kind: string;
  spec: string;
  acceptance: string[];
  inScope: string[];
  /**
   * The draft carries **one** verify command, not a list: `normalize_draft`
   * (`pipeline.py · _DRAFT_STR_KEYS`) projects this key with `str(...).strip()`, so an
   * array would be stored verbatim as the string `"[]"` and then land in the row's
   * `verify[]` as `["[]"]`. The array form is the *row* shape (`TaskNodeWire.verify`),
   * produced by `run_service._verify_list` — never send it here.
   */
  verify: string;
  dependsOn: string[];
  status: "todo";
  attempt: 0;
  round: 1;
  verdict: null;
  [key: string]: unknown;
}

/** The staged plan draft, verbatim as the backend stores it (`PlanDraft`). */
export interface PlanDraft {
  roles: string[];
  tasks: PlanTaskDraft[];
  updatedAt?: number | null;
  planStatus?: string | null;
  discarded?: { at?: number; reason?: string; taskCount?: number } | null;
}

/** Shared response shell of the three plan write routes (`PlanDraftOut`). */
export interface PlanDraftOut {
  draft: PlanDraft;
}

/**
 * The **derived** half of the plan gate — an extension of the single predicate above,
 * not a second parallel one: `isDecisionPending` stays the only place that reads the
 * decision status, and this only adds "and a draft is attached to it". Pass the payload
 * through both, so a draft left behind on a `resolved` decision never renders an editor.
 */
export function isPlanStaged(
  pending: Record<string, unknown> | null | undefined,
): boolean {
  return isDecisionPending(pending) && pending.draft != null;
}

/**
 * The only reader of the draft: it rides on `RunDetailOut.pending_decision`, there is no
 * dedicated read route. Gated by `isPlanStaged`, so a draft stranded on a resolved
 * payload reads as `null` and the caller keeps its read-only branch.
 */
export function readPlanDraft(run: RunDetailWire): PlanDraft | null {
  const pending = run.pending_decision;
  if (!isPlanStaged(pending)) {
    return null;
  }
  const draft = run.pending_decision?.draft;
  return draft == null ? null : (draft as PlanDraft);
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

/**
 * Stage (or re-stage) the plan draft: body `{ draft }`, one draft per run, last write
 * wins — a repeat call overwrites rather than queues. The draft parks the run inside
 * `pending_decision`, so `run.advance` keeps refusing until this is approved or dropped.
 */
export function planDraft(
  runId: string,
  draft: PlanDraft,
): Promise<PlanDraftOut> {
  return request<PlanDraftOut>(`/team/runs/${encodeURIComponent(runId)}:plan`, {
    method: "POST",
    body: JSON.stringify({ draft }),
  });
}

/**
 * Approve the staged draft. One merge write: rows already terminal are kept verbatim,
 * the rest are replaced by the draft, and both sides are judged before the first write so
 * a refusal leaves the board untouched. Returns the merged rows plus the kept settled ids
 * — for a count only; the task board must still be re-read from the tasks route.
 */
export function approvePlan(
  runId: string,
): Promise<{ tasks: TaskNodeWire[]; settledKept: string[] }> {
  return request<{ tasks: TaskNodeWire[]; settledKept: string[] }>(
    `/team/runs/${encodeURIComponent(runId)}:approve`,
    { method: "POST" },
  );
}

/**
 * Release the staged draft and cancel the pending decision. Run-level: the `draft` key is
 * removed but `team_runs.status` is untouched, so this is **not** an unpark — that stays
 * the resume route's call. The response only fills `discarded`; a repeat call is a 409.
 */
export function discardPlan(
  runId: string,
  reason?: string,
): Promise<PlanDraftOut> {
  return request<PlanDraftOut>(
    `/team/runs/${encodeURIComponent(runId)}:discard`,
    {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? "" }),
    },
  );
}

/** Storage statuses the UI cares about when counting "in flight" work. */
export const IN_FLIGHT_STATUSES: readonly TaskStorageStatus[] = [
  "planning",
  "todo",
  "doing",
  "review",
];
