// dashboard/src/pages/Kanban/index.tsx — Trello-style expert status board.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button, Input, Select } from "antd";
import { RefreshCw, Search } from "lucide-react";
import PageShell from "../../layouts/PageShell";
import { EmptyState } from "../../components/EmptyState";
import { CardSkeleton } from "../../components/Skeleton/CardSkeleton";
import { useAgent } from "../../context/AgentContext";
import { useServerTimezone } from "../../hooks/useServerTimezone";
import {
  octopAgentsApi,
  type KanbanOverviewAgent,
  type KanbanStatus,
} from "../../api/modules/octopAgents";
import { formatAgentError, formatAgentState } from "../../utils/agentError";
import { formatServerDateTime } from "../../utils/formatMessageTime";
import { apiErrorMessage } from "../../utils/apiError";
import { message } from "../../utils/antdMessage";
import { ExpertIcon } from "../Experts/components/iconForName";
import styles from "./index.module.less";

const POLL_INTERVAL_MS = 10_000;

const STATE_DOT: Record<string, { color: string; spin?: boolean }> = {
  running: { color: "#52c41a" },
  stopped: { color: "#8c8c8c" },
  created: { color: "#8c8c8c" },
  failed: { color: "#ff4d4f" },
  starting: { color: "#1677ff", spin: true },
  stopping: { color: "#1677ff", spin: true },
};

const COLUMN_META: Array<{
  status: KanbanStatus;
  labelKey: string;
  color: string;
}> = [
  { status: "needs_you", labelKey: "kanban.needsYou", color: "#faad14" },
  { status: "working", labelKey: "kanban.working", color: "#1677ff" },
  { status: "done", labelKey: "kanban.done", color: "#52c41a" },
  { status: "idle", labelKey: "kanban.idle", color: "#8c8c8c" },
];

type KindFilter = "all" | "expert" | "team";

function KanbanCard({
  agent,
  timezone,
  onOpen,
}: {
  agent: KanbanOverviewAgent;
  timezone: string;
  onOpen: (agent: KanbanOverviewAgent) => void;
}) {
  const { t } = useTranslation();
  const latest = agent.latest_thread;
  const snippet = latest?.message?.text ?? latest?.title ?? null;
  const dot = STATE_DOT[agent.state] ?? STATE_DOT.stopped;
  return (
    <div
      className={styles.card}
      onClick={() => onOpen(agent)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onOpen(agent);
      }}
    >
      {agent.hitl_pending || agent.pending_plan || agent.state === "failed" ? (
        <div className={styles.labels}>
          {agent.hitl_pending ? (
            <span className={`${styles.label} ${styles.labelHitl}`}>
              {t("kanban.hitlPending")}
              {agent.hitl_pending.count > 1
                ? ` ×${agent.hitl_pending.count}`
                : ""}
            </span>
          ) : null}
          {agent.pending_plan ? (
            <span className={`${styles.label} ${styles.labelPlan}`}>
              {t("kanban.pendingPlan")}
            </span>
          ) : null}
          {agent.state === "failed" ? (
            <span className={`${styles.label} ${styles.labelError}`}>
              {formatAgentState(agent.state, t)}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className={styles.cardTitle}>
        <ExpertIcon
          iconUrl={agent.icon_url}
          iconName={agent.icon_name}
          size={20}
          className={styles.cardIcon}
        />
        <span className={styles.cardName} title={agent.name}>
          {agent.name}
        </span>
        {agent.kind === "team" ? (
          <span className={styles.teamTag}>{t("kanban.teamTag")}</span>
        ) : null}
      </div>

      {agent.state === "failed" && agent.last_error ? (
        <div className={styles.errorLine} title={agent.last_error}>
          {formatAgentError(agent.last_error, t)}
        </div>
      ) : null}

      {snippet ? (
        <div className={styles.snippet}>{snippet}</div>
      ) : (
        <div className={styles.snippetEmpty}>{t("kanban.noConversation")}</div>
      )}

      <div className={styles.cardFooter}>
        <span className={styles.stateBadge}>
          <span
            className={dot.spin ? styles.stateDotSpin : styles.stateDot}
            style={{ backgroundColor: dot.color }}
          />
          {formatAgentState(agent.state, t)}
        </span>
        <span className={styles.cardTime}>
          {latest ? formatServerDateTime(latest.last_active, timezone) : ""}
        </span>
        {agent.unread_count && agent.unread_count > 0 ? (
          <span className={styles.unreadBadge}>
            {agent.unread_count > 99 ? "99+" : agent.unread_count}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export default function KanbanPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const timezone = useServerTimezone();
  const { setActiveAgent } = useAgent();
  const [agents, setAgents] = useState<KanbanOverviewAgent[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) setRefreshing(true);
      try {
        setAgents(await octopAgentsApi.overview());
      } catch (err) {
        message.error(apiErrorMessage(err, t("kanban.loadFailed"), t));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void load();
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") void load({ silent: true });
    }, POLL_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void load({ silent: true });
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (agents ?? []).filter((a) => {
      if (kindFilter !== "all" && (a.kind ?? "expert") !== kindFilter) {
        return false;
      }
      if (!q) return true;
      return (
        a.name.toLowerCase().includes(q) ||
        (a.description ?? "").toLowerCase().includes(q)
      );
    });
  }, [agents, search, kindFilter]);

  const columns = useMemo(
    () =>
      COLUMN_META.map((col) => ({
        ...col,
        cards: filtered
          .filter((a) => a.kanban_status === col.status)
          .sort(
            (a, b) =>
              (b.latest_thread?.last_active ?? 0) -
              (a.latest_thread?.last_active ?? 0),
          ),
      })),
    [filtered],
  );

  const openChat = useCallback(
    (agent: KanbanOverviewAgent) => {
      setActiveAgent(agent.agent_id);
      const targetThreadId =
        agent.attention_thread_id ?? agent.latest_thread?.thread_id ?? null;
      navigate(
        targetThreadId
          ? `/chat/${agent.agent_id}/${targetThreadId}`
          : `/chat/${agent.agent_id}`,
      );
    },
    [navigate, setActiveAgent],
  );

  return (
    <PageShell
      title={t("kanban.title")}
      subtitle={t("kanban.subtitle")}
      fill
      actions={
        <div className={styles.actions}>
          <Input
            allowClear
            className={styles.searchInput}
            prefix={<Search size={14} />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("kanban.searchPlaceholder")}
          />
          <Select<KindFilter>
            value={kindFilter}
            onChange={setKindFilter}
            className={styles.kindSelect}
            options={[
              { value: "all", label: t("kanban.filterAll") },
              { value: "expert", label: t("kanban.filterExperts") },
              { value: "team", label: t("kanban.filterTeams") },
            ]}
          />
          <Button
            icon={<RefreshCw size={14} />}
            loading={refreshing}
            onClick={() => void load()}
          >
            {t("kanban.refresh")}
          </Button>
        </div>
      }
    >
      {loading ? (
        <CardSkeleton count={4} />
      ) : (agents ?? []).length === 0 ? (
        <EmptyState
          variant="mascot"
          title={t("kanban.emptyTitle")}
          description={t("kanban.emptyDescription")}
          actionLabel={t("kanban.emptyAction")}
          onAction={() => navigate("/experts")}
        />
      ) : (
        <div className={styles.board}>
          {columns.map((col) => (
            <div key={col.status} className={styles.column}>
              <div className={styles.columnHeader}>
                <span
                  className={styles.columnDot}
                  style={{ backgroundColor: col.color }}
                />
                <span className={styles.columnTitle}>{t(col.labelKey)}</span>
                <span className={styles.columnCount}>{col.cards.length}</span>
              </div>
              <div className={styles.columnBody}>
                {col.cards.length === 0 ? (
                  <div className={styles.columnEmpty}>
                    {t("kanban.emptyColumn")}
                  </div>
                ) : (
                  col.cards.map((agent) => (
                    <KanbanCard
                      key={agent.agent_id}
                      agent={agent}
                      timezone={timezone}
                      onOpen={openChat}
                    />
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </PageShell>
  );
}
