import { Button, Drawer, Empty, Space, Spin } from "antd";
import { Download, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  trajectoryApi,
  type TrajectoryEvent,
  type TrajectoryMetrics,
} from "../../../api/modules/trajectory";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useTrajectorySession } from "../hooks/useTrajectorySession";
import {
  collapseCalls,
  collapseTurns,
  filterRows,
  toLedgerRow,
} from "../utils/trajectoryModel";
import {
  deriveSwimlaneSpans,
  trajectoryFocusEventIds,
  type TrajectoryTimeRange,
} from "../utils/trajectoryTimeline";
import styles from "./TrajectoryDrawer.module.less";
import TrajectoryInspector from "./TrajectoryInspector";
import TrajectoryLedger from "./TrajectoryLedger";
import TrajectoryMetricsBar from "./TrajectoryMetricsBar";
import TrajectoryTimeline from "./TrajectoryTimeline";
import TrajectoryToolbar from "./TrajectoryToolbar";

export interface TrajectoryDrawerProps {
  agentId: string;
  threadId: string | null;
  open: boolean;
  onClose: () => void;
}

function firstOfGroups(groups: TrajectoryEvent[][]): TrajectoryEvent[] {
  return groups.flatMap((group) => (group[0] != null ? [group[0]] : []));
}

function collapsedEvents(
  events: TrajectoryEvent[],
  collapseTurn: boolean,
  collapseCall: boolean,
): TrajectoryEvent[] {
  let rows = events;
  if (collapseTurn) {
    rows = firstOfGroups(collapseTurns(rows));
  }
  if (collapseCall) {
    rows = firstOfGroups(collapseCalls(rows));
  }
  return rows;
}

export default function TrajectoryDrawer({
  agentId,
  threadId,
  open,
  onClose,
}: TrajectoryDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const { events, loading, error, retry, hasMore, loadEarlier, refresh } =
    useTrajectorySession({
      agentId,
      threadId,
      visible: open,
    });
  const [durationOn, setDurationOn] = useState(false);
  const [collapseTurn, setCollapseTurn] = useState(false);
  const [collapseCall, setCollapseCall] = useState(false);
  const [query, setQuery] = useState("");
  const [range, setRange] = useState<TrajectoryTimeRange | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<TrajectoryMetrics | null>(null);

  useEffect(() => {
    setRange(null);
    setSelectedEventId(null);
    setQuery("");
    setCollapseTurn(false);
    setCollapseCall(false);
    setDurationOn(false);
  }, [agentId, threadId]);

  useEffect(() => {
    setMetrics(null);
    if (!open || !threadId) return;
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
  }, [open, agentId, threadId, events.length]);

  const mode = durationOn ? "duration" : "sequence";
  const ledgerEvents = useMemo(
    () => collapsedEvents(events, collapseTurn, collapseCall),
    [events, collapseTurn, collapseCall],
  );
  const searchMatchIds = useMemo(() => {
    if (!query.trim()) return null;
    return new Set(
      filterRows(ledgerEvents.map(toLedgerRow), query).map((row) => row.id),
    );
  }, [ledgerEvents, query]);
  const focusEventIds = useMemo(() => {
    if (range == null) return null;
    return trajectoryFocusEventIds(deriveSwimlaneSpans(events, mode), range);
  }, [events, mode, range]);
  const selectedEvent =
    events.find((event) => event.event_id === selectedEventId) ?? null;

  const onExport = () => {
    if (!threadId) return;
    void (async () => {
      const blob = await trajectoryApi.export(agentId, threadId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `trajectory-${threadId}.jsonl`;
      link.click();
      URL.revokeObjectURL(url);
    })();
  };

  const drawerTitle = (
    <div className={styles.drawerTitleRow}>
      <span className={styles.drawerTitleText}>
        {t("chat.dockTrajectoryTitle", "Trajectory")}
      </span>
      <Space size={isMobile ? 4 : 8} className={styles.drawerTitleActions}>
        <Button
          size="small"
          icon={<RefreshCw size={13} />}
          onClick={() => refresh()}
          aria-label={t("common.refresh", "Refresh")}
        >
          {isMobile ? null : t("common.refresh", "Refresh")}
        </Button>
        <Button
          size="small"
          icon={<Download size={13} />}
          disabled={!threadId}
          onClick={() => void onExport()}
          aria-label={t("chat.dockTrajectoryExport", "Export")}
        >
          {isMobile ? null : t("chat.dockTrajectoryExport", "Export")}
        </Button>
      </Space>
    </div>
  );

  let body: ReactNode;
  if (!threadId) {
    body = (
      <div className={styles.status}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t(
            "chat.dockTrajectorySelectSession",
            "Select a session to view trajectory",
          )}
        />
      </div>
    );
  } else if (loading && events.length === 0) {
    body = (
      <div className={styles.status}>
        <Spin size="small" />
      </div>
    );
  } else if (error && events.length === 0) {
    body = (
      <div className={styles.status}>
        <p className={styles.errorText}>
          {t("chat.dockTrajectoryLoadError", "Failed to load trajectory")}
        </p>
        <button type="button" className={styles.retry} onClick={retry}>
          {t("chat.retry", "Retry")}
        </button>
      </div>
    );
  } else if (events.length === 0) {
    body = (
      <div className={styles.status}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t(
            "chat.dockTrajectoryEmpty",
            "No trajectory events yet",
          )}
        />
      </div>
    );
  } else {
    body = (
      <>
        <TrajectoryToolbar
          durationOn={durationOn}
          onDurationOnChange={setDurationOn}
          allTurnsCollapsed={collapseTurn}
          onToggleAllTurns={() => setCollapseTurn((value) => !value)}
          allCallsCollapsed={collapseCall}
          onToggleAllCalls={() => setCollapseCall((value) => !value)}
          searchQuery={query}
          onSearchQueryChange={setQuery}
        />
        <TrajectoryTimeline
          events={events}
          mode={mode}
          range={range}
          onRangeChange={setRange}
          selectedEventId={selectedEventId}
          searchMatchIds={searchMatchIds}
          hasEarlier={hasMore}
          onLoadEarlier={loadEarlier}
          onRecordSelect={setSelectedEventId}
        />
        <div
          className={`${styles.split} ${isMobile ? styles.splitMobile : ""}`}
        >
          <div className={styles.ledgerPane}>
            <TrajectoryLedger
              events={ledgerEvents}
              selectedEventId={selectedEventId}
              onSelect={setSelectedEventId}
              focusEventIds={focusEventIds}
              searchMatchIds={searchMatchIds}
            />
          </div>
          <div className={styles.inspectorPane}>
            <TrajectoryInspector
              agentId={agentId}
              threadId={threadId}
              event={selectedEvent}
            />
          </div>
        </div>
        <TrajectoryMetricsBar
          agentId={agentId}
          threadId={threadId}
          metrics={metrics}
        />
      </>
    );
  }

  return (
    <Drawer
      title={drawerTitle}
      open={open}
      onClose={onClose}
      width={isMobile ? "100%" : "80vw"}
      destroyOnHidden
      styles={{
        body: {
          padding: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
      }}
    >
      <div className={styles.body}>{body}</div>
    </Drawer>
  );
}
