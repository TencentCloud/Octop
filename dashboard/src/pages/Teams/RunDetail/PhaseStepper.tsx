/**
 * `PhaseStepper` — the nine-phase pipeline, with the two facts that must stay visible.
 *
 * 1. **`skipped_roles`** (`gate_detail.skipped_roles`, written by
 *    `run_service.create()`): the tier cap cut these roles. AM-1's hard rule is
 *    「被裁可见、不静默丢弃」 — the UI is that requirement's visible face. A phase with
 *    cuts shows them as tags; we never fold them into a bare count.
 * 2. **`pending_decision`**: when the run is parked on a decision, the current phase is
 *    badged so the stepper does not read as "waiting for nothing".
 *
 * Presentational (AGENTS.md §5): no fetching, no writes — the caller passes phases in.
 */

import { Tag, Tooltip, Typography } from "antd";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import {
  isDecisionPending,
  type PhaseWire,
} from "../../../api/modules/teamRuns";

type Translate = TFunction;

/** Nine phases: two of them need a key-safe alias (hyphen / CJK). */
const PHASE_KEY: Record<string, string> = {
  "spec-review": "spec_review",
  方案确认: "confirm",
};

/** Phase display name; falls back to the raw phase (never an empty label). */
export function phaseLabel(phase: string, t: Translate): string {
  return t(`teamRuns.phaseName.${PHASE_KEY[phase] ?? phase}`, phase);
}

/** Phase status label (pending/active/passed/failed/skipped). */
export function phaseStatusLabel(status: string, t: Translate): string {
  return t(`teamRuns.phaseStatus.${status}`, status);
}

/** Gate details other than `skipped_roles` — shown as raw keys, never silently dropped. */
export function gateDetailKeys(
  gateDetail: Record<string, unknown> | undefined,
): string[] {
  return Object.keys(gateDetail ?? {}).filter((key) => key !== "skipped_roles");
}

/** Roles the tier cap dropped for this phase (`[]` when nothing was cut). */
export function skippedRolesOf(
  gateDetail: Record<string, unknown> | undefined,
): string[] {
  const raw = gateDetail?.skipped_roles;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (role): role is string => typeof role === "string" && role.length > 0,
  );
}

export interface PhaseStepperProps {
  phases: PhaseWire[];
  /**
   * The run's `pending_decision` payload. The badge is driven by
   * :func:`isDecisionPending`, not by presence: a **resolved** payload (which the backend
   * keeps on the run) must not keep a phase looking parked.
   */
  pendingDecision?: Record<string, unknown> | null;
}

export default function PhaseStepper({
  phases,
  pendingDecision,
}: PhaseStepperProps) {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-wrap items-center gap-2"
      data-testid="phase-stepper"
    >
      {phases.map((phase) => {
        const skipped = skippedRolesOf(phase.gate_detail);
        const parked =
          isDecisionPending(pendingDecision) && phase.status === "active";
        return (
          <div
            key={`${phase.seq}-${phase.phase}`}
            data-testid={`phase-${phase.phase}`}
            data-status={phase.status}
            className="rounded border px-2 py-1 text-sm"
          >
            <div className="flex items-center gap-1">
              <span>{phaseLabel(phase.phase, t)}</span>
              <Tag data-testid={`phase-status-${phase.phase}`}>
                {phaseStatusLabel(phase.status, t)}
              </Tag>
              {parked ? (
                <Tag color="orange" data-testid={`phase-parked-${phase.phase}`}>
                  {t("teamRuns.phase.pendingDecision")}
                </Tag>
              ) : null}
            </div>
            {gateDetailKeys(phase.gate_detail).length > 0 ? (
              <div
                className="mt-1 text-xs opacity-70"
                data-testid={`phase-gate-detail-${phase.phase}`}
              >
                {t("teamRuns.gate.detailLabel")}:{" "}
                {gateDetailKeys(phase.gate_detail).join(", ")}
              </div>
            ) : null}
            {skipped.length > 0 ? (
              <div
                className="mt-1 flex flex-wrap gap-1"
                data-testid={`phase-skipped-${phase.phase}`}
              >
                <Tooltip title={t("teamRuns.phase.skippedHint")}>
                  <Typography.Text type="secondary" className="text-xs">
                    {t("teamRuns.phase.skippedLabel")}
                  </Typography.Text>
                </Tooltip>
                {skipped.map((role) => (
                  <Tag key={role} color="default">
                    {role}
                  </Tag>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
