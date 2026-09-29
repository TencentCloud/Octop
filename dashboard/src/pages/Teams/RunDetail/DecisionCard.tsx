/**
 * `DecisionCard` — the run is parked (`awaiting_confirmation` / `awaiting_decision`).
 *
 * **Only a *pending* decision renders as pending.** `RunDetailOut.pending_decision` is
 * **not cleared** once it is taken: `decide()` writes the same payload back with
 * `status: "resolved"` (`run_service.py:1223`). So this card checks
 * :func:`isDecisionPending` itself and shows the "no pending decision" state for a
 * resolved payload — otherwise it would offer a confirm affordance for a decision that
 * has already been made (the defect T-53 fixed).
 *
 * The card shows the pending decision as **stored data** (`decision_id`, and whatever
 * the run carries in `pending_decision`), plus the choices the caller passes in. It does
 * **not** invent options: if the payload carries no option list, the card says the run is
 * parked and leaves choosing to the caller's `onDecide` — an invented default would be
 * exactly the "silence read as a decision" failure this run keeps hitting.
 *
 * Presentational (AGENTS.md §5): no fetching — the caller owns the request. Every write
 * affordance is a callback prop (`onDecide`, `onStageDraft`, `onApprovePlan`,
 * `onDiscardPlan`); a callback that is absent disables its own control, so a caller that
 * passes none of them keeps today's read-only card.
 *
 * The **plan editor** rides on top of the read-only pending state and is gated by
 * :func:`isPlanStaged` *after* the `decision-none` early return — so the early return keeps
 * winning (a draft stranded on a resolved decision renders no editor, T-53's guard) and a
 * pending decision without a draft stays exactly as it was.
 */

import {
  Alert,
  Button,
  Descriptions,
  Input,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  isDecisionPending,
  isPlanStaged,
  type PlanDraft,
  type PlanTaskDraft,
} from "../../../api/modules/teamRuns";

export interface DecisionOption {
  id: string;
  label: string;
}

/**
 * A brand-new row, blank on purpose. The backend projects every row through its own key
 * set (`pipeline.py · _DRAFT_STR_KEYS`) and refuses a blank `owner` / empty `inScope` with
 * a 422 — so the card submits `owner: ""` **as is** rather than auto-picking a role to make
 * a half-filled row look valid.
 */
const NEW_TASK: PlanTaskDraft = {
  id: "",
  owner: "",
  title: "",
  kind: "",
  spec: "",
  acceptance: [],
  inScope: [],
  // One command, not a list — `pipeline.py · _DRAFT_STR_KEYS` string-projects this key.
  verify: "",
  dependsOn: [],
  status: "todo",
  attempt: 0,
  round: 1,
  verdict: null,
};

export interface DecisionCardProps {
  /**
   * `RunDetailOut.pending_decision`. Passed through as-is: the card applies
   * :func:`isDecisionPending` itself, so a resolved payload renders the "no pending
   * decision" state instead of a stale confirm affordance.
   */
  pendingDecision: Record<string, unknown> | null;
  /** Choices offered by the caller; empty ⇒ confirm-only affordance. */
  options?: DecisionOption[];
  onDecide?: (choice: string) => void;
  busy?: boolean;
  /**
   * `readPlanDraft(run)`: the staged plan draft. Absent / `null` ⇒ the pending decision is
   * shown read-only, exactly as before — the editor is never rendered from truthiness.
   */
  draft?: PlanDraft | null;
  /** Stage the edited draft (`{ draft }`); one draft per run, a repeat overwrites it. */
  onStageDraft?: (draft: PlanDraft) => Promise<void>;
  /** Approve the staged draft; the board is re-read by the caller, never patched here. */
  onApprovePlan?: () => Promise<void>;
  /** Drop the staged draft; `reason` is optional and recorded with the run. */
  onDiscardPlan?: (reason?: string) => Promise<void>;
}

function readString(
  source: Record<string, unknown>,
  key: string,
): string | null {
  const value = source[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export default function DecisionCard({
  pendingDecision,
  options = [],
  onDecide,
  busy,
  draft = null,
  onStageDraft,
  onApprovePlan,
  onDiscardPlan,
}: DecisionCardProps) {
  const { t } = useTranslation();
  // The **edit buffer**: a copy of the server draft, re-seeded whenever a re-read hands us
  // a new object (or `null` once the draft is dropped) — the server stays the one source of
  // truth, and nothing here is optimistic.
  const [edited, setEdited] = useState<PlanDraft | null>(draft);
  const [reason, setReason] = useState("");
  useEffect(() => {
    setEdited(draft);
  }, [draft]);

  if (!isDecisionPending(pendingDecision)) {
    return (
      <Alert
        type="success"
        showIcon
        data-testid="decision-none"
        message={t("teamRuns.decision.none")}
      />
    );
  }
  const decisionId =
    readString(pendingDecision, "decision_id") ??
    readString(pendingDecision, "id");
  const kind = readString(pendingDecision, "kind");
  const question =
    readString(pendingDecision, "question") ??
    readString(pendingDecision, "title");
  // Two gates, in order. `isPlanStaged` decides *whether* a draft is editable at all (the
  // `decision-none` early return above already ruled on `pending`); the callback checks
  // decide *what* is editable — an absent callback disables its own control and nothing
  // else, so a caller that injects no writers keeps the read-only card.
  const staged = isPlanStaged(pendingDecision);
  const draftValue = edited;
  const canEdit = !busy && onStageDraft !== undefined;
  const canDiscard = !busy && onDiscardPlan !== undefined;
  const emptyTasks = (draftValue?.tasks.length ?? 0) === 0;
  // A draft the backend will refuse is still submitted as is (422 `owner-not-in-roles`):
  // this is a warning, never a client-side "fix" — no role is picked on the user's behalf.
  const ownerOutsideRoles =
    draftValue !== null &&
    draftValue.roles.length > 0 &&
    draftValue.tasks.some((task) => !draftValue.roles.includes(task.owner));

  /** Copy-then-patch one row: only the edited key is replaced, every other key survives. */
  const patchTask = (index: number, patch: Partial<PlanTaskDraft>) => {
    setEdited((current) =>
      current === null
        ? current
        : {
            ...current,
            tasks: current.tasks.map((task, at) =>
              at === index ? { ...task, ...patch } : task,
            ),
          },
    );
  };
  const addTask = () => {
    setEdited((current) =>
      current === null
        ? current
        : {
            ...current,
            tasks: [...current.tasks, { ...NEW_TASK, id: crypto.randomUUID() }],
          },
    );
  };
  const removeTask = (index: number) => {
    setEdited((current) =>
      current === null
        ? current
        : { ...current, tasks: current.tasks.filter((_, at) => at !== index) },
    );
  };
  return (
    <div data-testid="decision-card" className="flex flex-col gap-2">
      <Alert
        type="warning"
        showIcon
        message={t("teamRuns.decision.pending")}
        description={question ?? t("teamRuns.decision.pendingHint")}
      />
      <Descriptions size="small" column={1}>
        <Descriptions.Item label={t("teamRuns.decision.id")}>
          <span data-testid="decision-id">
            {decisionId ?? t("teamRuns.decision.idMissing")}
          </span>
        </Descriptions.Item>
        <Descriptions.Item label={t("teamRuns.decision.kind")}>
          {kind ?? (
            <Typography.Text type="secondary">
              {t("teamRuns.decision.kindMissing")}
            </Typography.Text>
          )}
        </Descriptions.Item>
      </Descriptions>
      {options.length > 0 ? (
        <Space wrap data-testid="decision-options">
          {options.map((option) => (
            <Button
              key={option.id}
              disabled={busy || !onDecide}
              onClick={() => onDecide?.(option.id)}
              data-testid={`decision-option-${option.id}`}
            >
              {option.label}
            </Button>
          ))}
        </Space>
      ) : (
        <Tag data-testid="decision-no-options">
          {t("teamRuns.decision.noOptions")}
        </Tag>
      )}
      {staged && draftValue !== null ? (
        <div data-testid="plan-editor" className="flex flex-col gap-2">
          <Typography.Text strong>{t("teamRuns.plan.title")}</Typography.Text>
          <Typography.Text type="secondary">
            {t("teamRuns.plan.hint")}
          </Typography.Text>
          {draftValue.planStatus === "staged" ? (
            <Tag data-testid="plan-staged">{t("teamRuns.plan.staged")}</Tag>
          ) : null}
          {draftValue.roles.length === 0 ? (
            <Typography.Text type="warning" data-testid="plan-owner-missing">
              {t("teamRuns.plan.ownerMissing")}
            </Typography.Text>
          ) : null}
          {ownerOutsideRoles ? (
            <Typography.Text type="warning" data-testid="plan-draft-invalid">
              {t("teamRuns.plan.draftInvalid")}
            </Typography.Text>
          ) : null}
          {emptyTasks ? (
            <Typography.Text type="warning" data-testid="plan-tasks-empty">
              {t("teamRuns.plan.tasksEmpty")}
            </Typography.Text>
          ) : null}
          {draftValue.tasks.map((task, index) => (
            <div
              key={task.id === "" ? index : task.id}
              data-testid="plan-task"
              className="flex flex-wrap items-center gap-2"
            >
              <Select
                data-testid={`plan-owner-${task.id}`}
                value={task.owner === "" ? undefined : task.owner}
                options={draftValue.roles.map((role) => ({
                  value: role,
                  label: role,
                }))}
                placeholder={t("teamRuns.plan.owner")}
                disabled={!canEdit}
                onChange={(value: string) => patchTask(index, { owner: value })}
              />
              <Input
                data-testid={`plan-title-${task.id}`}
                value={task.title}
                addonBefore={t("teamRuns.plan.taskTitle")}
                disabled={!canEdit}
                onChange={(event) =>
                  patchTask(index, { title: event.target.value })
                }
              />
              <Typography.Text type="secondary">
                {t("teamRuns.plan.deps")}
              </Typography.Text>
              <Select
                mode="multiple"
                data-testid={`plan-deps-${task.id}`}
                value={task.dependsOn}
                // Every id on the draft, this row's own included: a self-dependency is
                // refused by the backend (`self-dependency`), and pre-filtering it here
                // would hide a refusal the user is entitled to see.
                options={draftValue.tasks.map((other) => ({
                  value: other.id,
                  label: other.id,
                }))}
                placeholder={t("teamRuns.plan.depsPlaceholder")}
                disabled={!canEdit}
                onChange={(value: string[]) =>
                  patchTask(index, { dependsOn: value })
                }
              />
              <Button
                size="small"
                disabled={!canEdit}
                data-testid={`plan-remove-${task.id}`}
                onClick={() => removeTask(index)}
              >
                {t("teamRuns.plan.removeTask")}
              </Button>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="primary"
              disabled={busy || !onStageDraft}
              data-testid="plan-stage"
              onClick={() => {
                if (onStageDraft) void onStageDraft(draftValue);
              }}
            >
              {t("teamRuns.plan.stage")}
            </Button>
            <Button
              disabled={busy || !onApprovePlan || emptyTasks}
              data-testid="plan-approve"
              onClick={() => {
                if (onApprovePlan) void onApprovePlan();
              }}
            >
              {t("teamRuns.plan.approve")}
            </Button>
            <Button
              danger
              disabled={busy || !onDiscardPlan}
              data-testid="plan-discard"
              onClick={() => {
                if (onDiscardPlan) void onDiscardPlan(reason);
              }}
            >
              {t("teamRuns.plan.discard")}
            </Button>
          </div>
          <Input
            data-testid="plan-discard-reason"
            value={reason}
            addonBefore={t("teamRuns.plan.discardReason")}
            placeholder={t("teamRuns.plan.discardReasonPlaceholder")}
            disabled={!canDiscard}
            onChange={(event) => setReason(event.target.value)}
          />
          <Button disabled={!canEdit} data-testid="plan-add" onClick={addTask}>
            {t("teamRuns.plan.addTask")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
