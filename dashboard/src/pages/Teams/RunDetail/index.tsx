/**
 * `RunDetail` — the run page: a gate red bar on top, then the tabs.
 *
 * Data loading follows T-16's progressive contract: `GET /state?section=…` fills one
 * slice at a time (`summary` / `people` / `feed` / `artifacts` / `tasks` / `check`), so
 * the page paints the summary first and pulls the heavy slices per tab. `metrics` is its
 * own route because it rolls up a different source.
 *
 * ★ The **gate red bar** is this page's reason to exist: it surfaces, on every tab,
 * (a) `pending_decision` (the run is parked — nothing advances until a human chooses) and
 * (b) `skipped_roles` from `phases[].gate_detail` (the tier cap cut roles — AM-1 requires
 * that to stay visible, never silently dropped). Both are stated as facts; neither is
 * folded into a count.
 *
 * Boundary (AGENTS.md §5): this page owns the requests (via `api/modules/teamRuns`); the
 * child components are presentational and receive props. No component fetches directly.
 */

import {
  Alert,
  Button,
  Empty,
  Result,
  Spin,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  getMetrics,
  getRun,
  getRunState,
  isDecisionPending,
  listArtifacts,
  listTasks,
  type ArtifactItemWire,
  type MetricsWire,
  type RunDetailWire,
  type TaskBoardWire,
  type TaskNodeWire,
} from "../../../api/modules/teamRuns";
import ArtifactPanel from "./ArtifactPanel";
import DecisionCard from "./DecisionCard";
import MetricsTab from "./MetricsTab";
import PeoplePanel from "./PeoplePanel";
import PhaseStepper, { skippedRolesOf } from "./PhaseStepper";
import TaskGraph from "./TaskGraph";

/** Every role the tier cap cut anywhere in the run, in phase order (deduped). */
export function allSkippedRoles(phases: RunDetailWire["phases"]): string[] {
  const seen: string[] = [];
  for (const phase of phases) {
    for (const role of skippedRolesOf(phase.gate_detail)) {
      if (!seen.includes(role)) seen.push(role);
    }
  }
  return seen;
}

export interface RunDetailProps {
  runId: string;
  /** Optional pre-fetched detail (e.g. from the list page) to avoid a first paint flicker. */
  initialDetail?: RunDetailWire | null;
}

export default function RunDetail({
  runId,
  initialDetail = null,
}: RunDetailProps) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<RunDetailWire | null>(initialDetail);
  const [tasks, setTasks] = useState<TaskNodeWire[]>([]);
  const [board, setBoard] = useState<TaskBoardWire | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactItemWire[]>([]);
  const [metrics, setMetrics] = useState<MetricsWire | null>(null);
  const [checkViolations, setCheckViolations] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // `GET /{run_id}` is the one route that carries `pending_decision` + phases +
      // members together (`RunDetailOut`); `state?section=…` is the progressive slice
      // used here for the read-side check (which never blocks).
      const [detailResult, check] = await Promise.all([
        getRun(runId),
        getRunState(runId, "check"),
      ]);
      setNotFound(false);
      setDetail(detailResult);
      setCheckViolations(check.check?.violations ?? []);
      const [boardResult, artifactResult, metricsResult] = await Promise.all([
        listTasks(runId),
        listArtifacts(runId),
        getMetrics(runId),
      ]);
      setBoard(boardResult);
      setTasks(boardResult.nodes);
      setArtifacts(artifactResult.items);
      setMetrics(metricsResult);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      // A missing run is **its own state**: a visible "not found" page, never a blank
      // screen and never a generic error (the positive control for T-21 acceptance ③).
      if (/\b404\b/.test(message)) {
        setNotFound(true);
        setError(null);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const skipped = useMemo(
    () => (detail ? allSkippedRoles(detail.phases) : []),
    [detail],
  );
  // `pending_decision` is **not cleared** when a decision is taken (`decide()` writes the
  // same payload back with `status: "resolved"`), so the payload's presence says nothing.
  // Every consumer below uses the one predicate instead of truthiness.
  const rawDecision = detail?.pending_decision ?? null;
  const pendingDecision = isDecisionPending(rawDecision) ? rawDecision : null;

  if (notFound) {
    return (
      <div data-testid="run-not-found">
        <Result
          status="404"
          title={t("teamRuns.notFound.title")}
          subTitle={t("teamRuns.notFound.hint")}
          extra={
            <Button
              onClick={() => void load()}
              data-testid="run-not-found-retry"
            >
              {t("teamRuns.notFound.back")}
            </Button>
          }
        />
      </div>
    );
  }
  if (error) {
    return (
      <Alert type="error" showIcon data-testid="run-error" message={error} />
    );
  }
  if (!detail) {
    return <Spin data-testid="run-loading" />;
  }

  return (
    <div data-testid="run-detail" className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Typography.Title level={4} className="m-0">
          {detail.goal}
        </Typography.Title>
        <Tag data-testid="run-status">
          {t(`teamRuns.runStatus.${detail.status}`, detail.status)}
        </Tag>
        <Button
          size="small"
          onClick={() => void load()}
          data-testid="run-refresh"
        >
          {t("teamRuns.action.refresh")}
        </Button>
        <Tag data-testid="run-tier">{detail.tier}</Tag>
      </div>

      <div data-testid="gate-bar" className="flex flex-col gap-1">
        {pendingDecision ? (
          <Alert
            type="warning"
            showIcon
            data-testid="gate-pending-decision"
            message={t("teamRuns.gate.pendingDecision")}
          />
        ) : null}
        {skipped.length > 0 ? (
          <Alert
            type="info"
            showIcon
            data-testid="gate-skipped-roles"
            message={t("teamRuns.gate.skippedRoles")}
            description={
              <span data-testid="gate-skipped-list">{skipped.join(" / ")}</span>
            }
          />
        ) : null}
        {!pendingDecision && skipped.length === 0 ? (
          <Typography.Text type="secondary" data-testid="gate-clear">
            {t("teamRuns.gate.clear")}
          </Typography.Text>
        ) : null}
        {checkViolations.length > 0 ? (
          <Typography.Text type="warning" data-testid="gate-check-violations">
            {t("teamRuns.gate.checkViolations", {
              count: checkViolations.length,
            })}
            : {checkViolations.join(" / ")}
          </Typography.Text>
        ) : null}
      </div>

      <PhaseStepper phases={detail.phases} pendingDecision={pendingDecision} />

      <Tabs
        items={[
          {
            key: "people",
            label: t("teamRuns.tab.people"),
            children: (
              <PeoplePanel
                members={detail.members}
                tasks={tasks}
                loading={loading}
              />
            ),
          },
          {
            key: "tasks",
            label: t("teamRuns.tab.tasks"),
            children: <TaskGraph board={board} loading={loading} />,
          },
          {
            key: "artifacts",
            label: t("teamRuns.tab.artifacts"),
            children: <ArtifactPanel items={artifacts} loading={loading} />,
          },
          {
            key: "decision",
            label: t("teamRuns.tab.decision"),
            children: <DecisionCard pendingDecision={pendingDecision} />,
          },
          {
            key: "metrics",
            label: t("teamRuns.tab.metrics"),
            children: <MetricsTab metrics={metrics} loading={loading} />,
          },
        ]}
      />
      {detail.phases.length === 0 ? (
        <Empty
          data-testid="phases-empty"
          description={t("teamRuns.phase.none")}
        />
      ) : null}
    </div>
  );
}
