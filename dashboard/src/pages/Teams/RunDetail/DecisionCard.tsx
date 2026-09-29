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
 * Presentational (AGENTS.md §5): no fetching — the caller owns the request. The optional
 * `onDecide` prop is the only write affordance; without it the card is read-only.
 */

import { Alert, Button, Descriptions, Space, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";

import { isDecisionPending } from "../../../api/modules/teamRuns";

export interface DecisionOption {
  id: string;
  label: string;
}

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
}: DecisionCardProps) {
  const { t } = useTranslation();
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
    </div>
  );
}
