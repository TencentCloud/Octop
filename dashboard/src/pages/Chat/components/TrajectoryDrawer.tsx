import { Button, Drawer, Empty, Space, Spin } from "antd";
import { Download, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { trajectoryApi } from "../../../api/modules/trajectory";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useTrajectorySession } from "../hooks/useTrajectorySession";
import {
  collapseCallRows,
  collapseTurnRows,
  collapsibleAssistantIds,
  ensureToolCallParents,
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

const EMPTY_IDS = new Set<string>();

export default function TrajectoryDrawer({
  agentId,
  threadId,
  open,
  onClose,
}: TrajectoryDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const {
    events,
    metrics,
    loading,
    error,
    retry,
    hasMore,
    loadEarlier,
    refresh,
  } = useTrajectorySession({
    agentId,
    threadId,
    visible: open,
  });
  const [durationOn, setDurationOn] = useState(false);
  const [collapseTurn, setCollapseTurn] = useState(false);
  const [collapsedAssistants, setCollapsedAssistants] =
    useState<ReadonlySet<string>>(EMPTY_IDS);
  const [query, setQuery] = useState("");
  const [range, setRange] = useState<TrajectoryTimeRange | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  useEffect(() => {
    setRange(null);
    setSelectedEventId(null);
    setQuery("");
    setCollapseTurn(false);
    setCollapsedAssistants(EMPTY_IDS);
    setDurationOn(false);
  }, [agentId, threadId]);

  const mode = durationOn ? "duration" : "sequence";
  const toolCallOnlyLabel = t(
    "chat.trajectoryToolCallOnly",
    "(tool call only)",
  );
  const formatCallSummary = (count: number, names: readonly string[]) => {
    const namesJoined = names.join(", ");
    if (count === 1) {
      return t(
        "chat.trajectoryCollapsedToolCallOne",
        "{{count}} tool call · {{names}}",
        { count, names: namesJoined },
      );
    }
    return t(
      "chat.trajectoryCollapsedToolCallMany",
      "{{count}} tool calls · {{names}}",
      { count, names: namesJoined },
    );
  };
  const formatTurnSummary = (steps: number, toolCalls: number) =>
    t(
      "chat.trajectoryCollapsedTurn",
      "{{steps}} steps · {{toolCalls}} tool calls",
      { steps, toolCalls },
    );

  const displayEvents = useMemo(
    () => ensureToolCallParents(events, toolCallOnlyLabel),
    [events, toolCallOnlyLabel],
  );
  const assistantIdsWithTools = useMemo(
    () => collapsibleAssistantIds(displayEvents),
    [displayEvents],
  );
  const allCallsCollapsed =
    assistantIdsWithTools.length > 0 &&
    assistantIdsWithTools.every((id) => collapsedAssistants.has(id));

  const ledgerEvents = useMemo(() => {
    let rows = displayEvents;
    if (collapseTurn) {
      rows = collapseTurnRows(rows, formatTurnSummary);
    }
    if (collapsedAssistants.size > 0) {
      rows = collapseCallRows(rows, formatCallSummary, collapsedAssistants);
    }
    return rows;
  }, [displayEvents, collapseTurn, collapsedAssistants, t]);

  const searchMatchIds = useMemo(() => {
    if (!query.trim()) return null;
    return new Set(
      filterRows(displayEvents.map(toLedgerRow), query).map((row) => row.id),
    );
  }, [displayEvents, query]);
  const focusEventIds = useMemo(() => {
    if (range == null) return null;
    return trajectoryFocusEventIds(
      deriveSwimlaneSpans(displayEvents, mode),
      range,
    );
  }, [displayEvents, mode, range]);
  const selectedEvent =
    displayEvents.find((event) => event.event_id === selectedEventId) ?? null;

  const toggleAllCalls = () => {
    setCollapsedAssistants(() => {
      if (allCallsCollapsed) return EMPTY_IDS;
      return new Set(assistantIdsWithTools);
    });
  };

  const onExpandCollapsed = (
    parentEventId: string,
    kind: "assistant" | "turn",
  ) => {
    if (kind === "turn") {
      setCollapseTurn(false);
      return;
    }
    setCollapsedAssistants((current) => {
      if (!current.has(parentEventId)) return current;
      const next = new Set(current);
      next.delete(parentEventId);
      return next.size === 0 ? EMPTY_IDS : next;
    });
  };

  const onExport = () => {
    if (!threadId) return;
    void (async () => {
      try {
        const blob = await trajectoryApi.export(agentId, threadId);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `trajectory-${threadId}.jsonl`;
        link.click();
        URL.revokeObjectURL(url);
      } catch {
        message.error(
          t("chat.trajectoryExportFailed", "Failed to export trajectory"),
        );
      }
    })();
  };

  const drawerTitle = (
    <div className={styles.drawerTitleRow}>
      <span className={styles.drawerTitleText}>
        {t("chat.trajectoryTitle", "Trajectory")}
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
          aria-label={t("chat.trajectoryExport", "Export")}
        >
          {isMobile ? null : t("chat.trajectoryExport", "Export")}
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
            "chat.trajectorySelectSession",
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
          {t("chat.trajectoryLoadError", "Failed to load trajectory")}
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
          description={t("chat.trajectoryEmpty", "No trajectory events yet")}
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
          allCallsCollapsed={allCallsCollapsed}
          onToggleAllCalls={toggleAllCalls}
          searchQuery={query}
          onSearchQueryChange={setQuery}
        />
        <TrajectoryTimeline
          events={displayEvents}
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
              onExpandCollapsed={onExpandCollapsed}
              focusEventIds={focusEventIds}
              searchMatchIds={searchMatchIds}
            />
          </div>
          <div
            className={styles.inspectorPane}
            data-testid="trajectory-inspector-pane"
          >
            <TrajectoryInspector
              agentId={agentId}
              threadId={threadId}
              event={selectedEvent}
              events={displayEvents}
              onSelectEvent={setSelectedEventId}
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
