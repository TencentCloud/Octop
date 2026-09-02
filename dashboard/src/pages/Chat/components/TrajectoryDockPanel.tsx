import { Empty, Spin } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  trajectoryApi,
  type TrajectoryEvent,
  type TrajectoryMetrics,
} from "../../../api/modules/trajectory";
import { useTrajectorySession } from "../hooks/useTrajectorySession";
import dockStyles from "../index.module.less";
import {
  collapseCalls,
  collapseTurns,
  filterRows,
  toLedgerRow,
} from "../utils/trajectoryModel";
import type { SwimlaneMode, SwimlaneSpan } from "../utils/trajectoryTimeline";
import styles from "./TrajectoryDockPanel.module.less";
import TrajectoryLedger from "./TrajectoryLedger";
import TrajectoryMetricsBar from "./TrajectoryMetricsBar";
import TrajectoryTimeline from "./TrajectoryTimeline";

interface TrajectoryDockPanelProps {
  agentId?: string;
  threadId?: string | null;
  /** False while the dock is closed or another tab is active (keep-alive). */
  visible?: boolean;
}

function firstOfGroups(groups: TrajectoryEvent[][]): TrajectoryEvent[] {
  return groups.flatMap((group) => (group[0] != null ? [group[0]] : []));
}

function ledgerEvents(
  events: TrajectoryEvent[],
  options: {
    focusedSpan: SwimlaneSpan | null;
    collapseTurn: boolean;
    collapseCall: boolean;
    query: string;
  },
): TrajectoryEvent[] {
  let rows = events;
  if (options.focusedSpan) {
    const ids = new Set(options.focusedSpan.eventIds);
    rows = rows.filter((event) => ids.has(event.event_id));
  }
  if (options.collapseTurn) {
    rows = firstOfGroups(collapseTurns(rows));
  }
  if (options.collapseCall) {
    rows = firstOfGroups(collapseCalls(rows));
  }
  if (options.query.trim()) {
    const matched = new Set(
      filterRows(rows.map(toLedgerRow), options.query).map((row) => row.id),
    );
    rows = rows.filter((event) => matched.has(event.event_id));
  }
  return rows;
}

export default function TrajectoryDockPanel({
  agentId,
  threadId = null,
  visible = true,
}: TrajectoryDockPanelProps) {
  const { t } = useTranslation();
  const { events, loading, error, retry } = useTrajectorySession({
    agentId,
    threadId,
    visible,
  });
  const [mode, setMode] = useState<SwimlaneMode>("sequence");
  const [collapseTurn, setCollapseTurn] = useState(false);
  const [collapseCall, setCollapseCall] = useState(false);
  const [query, setQuery] = useState("");
  const [focusedSpan, setFocusedSpan] = useState<SwimlaneSpan | null>(null);
  const [metrics, setMetrics] = useState<TrajectoryMetrics | null>(null);

  useEffect(() => {
    setMetrics(null);
    if (!visible || !agentId || !threadId) return;
    let cancelled = false;
    void trajectoryApi
      .metrics(agentId, threadId)
      .then((next) => {
        if (!cancelled) setMetrics(next);
      })
      .catch(() => {
        if (!cancelled) setMetrics(null);
      });
    return () => {
      cancelled = true;
    };
  }, [visible, agentId, threadId, events.length]);

  const visibleEvents = useMemo(
    () =>
      ledgerEvents(events, {
        focusedSpan,
        collapseTurn,
        collapseCall,
        query,
      }),
    [events, focusedSpan, collapseTurn, collapseCall, query],
  );

  if (!threadId) {
    return (
      <div className={dockStyles.dockFileListEmpty}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t(
            "chat.dockTrajectorySelectSession",
            "Select a session to view trajectory",
          )}
        />
      </div>
    );
  }

  if (loading && events.length === 0) {
    return (
      <div className={styles.status}>
        <Spin size="small" />
      </div>
    );
  }

  if (error && events.length === 0) {
    return (
      <div className={styles.status}>
        <p className={styles.errorText}>
          {t("chat.dockTrajectoryLoadError", "Failed to load trajectory")}
        </p>
        <button type="button" className={styles.retry} onClick={retry}>
          {t("chat.retry", "Retry")}
        </button>
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className={dockStyles.dockFileListEmpty}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t(
            "chat.dockTrajectoryEmpty",
            "No trajectory events yet",
          )}
        />
      </div>
    );
  }

  return (
    <div className={styles.root}>
      {agentId ? (
        <TrajectoryMetricsBar
          agentId={agentId}
          threadId={threadId}
          metrics={metrics}
        />
      ) : null}
      <div className={styles.toolbar}>
        <label className={styles.modeLabel}>
          <span className={styles.modeText}>
            {t("chat.dockTrajectoryMode", "Time scale")}
          </span>
          <select
            className={styles.modeSelect}
            aria-label={t("chat.dockTrajectoryMode", "Time scale")}
            value={mode}
            onChange={(event) => setMode(event.target.value as SwimlaneMode)}
          >
            <option value="sequence">
              {t("chat.dockTrajectoryModeSequence", "Sequence")}
            </option>
            <option value="duration">
              {t("chat.dockTrajectoryModeDuration", "Duration")}
            </option>
            <option value="actual">
              {t("chat.dockTrajectoryModeActual", "Actual time")}
            </option>
          </select>
        </label>
        <button
          type="button"
          className={styles.toggle}
          aria-pressed={collapseTurn}
          onClick={() => setCollapseTurn((value) => !value)}
        >
          {t("chat.dockTrajectoryCollapseTurns", "Collapse turns")}
        </button>
        <button
          type="button"
          className={styles.toggle}
          aria-pressed={collapseCall}
          onClick={() => setCollapseCall((value) => !value)}
        >
          {t("chat.dockTrajectoryCollapseCalls", "Collapse calls")}
        </button>
        <input
          type="search"
          className={styles.search}
          value={query}
          placeholder={t("chat.dockTrajectorySearch", "Search trajectory")}
          aria-label={t("chat.dockTrajectorySearch", "Search trajectory")}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <TrajectoryTimeline
        events={events}
        mode={mode === "duration" ? "duration" : "sequence"}
        range={null}
        onRangeChange={() => {}}
        selectedEventId={focusedSpan?.id ?? null}
        searchMatchIds={null}
        onRecordSelect={(eventId) => {
          setFocusedSpan({
            id: eventId,
            lane: "input",
            kind: "user",
            start: 0,
            end: 1,
            eventIds: [eventId],
            isError: false,
          });
        }}
      />
      {agentId ? (
        <TrajectoryLedger
          agentId={agentId}
          threadId={threadId}
          events={visibleEvents}
        />
      ) : null}
    </div>
  );
}
