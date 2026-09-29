// dashboard/src/pages/Kanban/index.tsx — Live expert status board.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
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
  type KanbanActivityState,
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

const COLUMN_META: Array<{
  status: KanbanStatus;
  labelKey: string;
}> = [
  { status: "needs_you", labelKey: "kanban.needsYou" },
  { status: "working", labelKey: "kanban.working" },
  { status: "done", labelKey: "kanban.done" },
  { status: "idle", labelKey: "kanban.idle" },
];

type KindFilter = "all" | "expert" | "team";

function displayActivity(
  activity: KanbanActivityState,
  unseen: boolean | undefined,
): KanbanActivityState {
  // Mirror server FSM: completed work settles to idle once acknowledged.
  if (activity === "done" && unseen === false) {
    return "idle";
  }
  return activity;
}

function activityLabel(
  activity: KanbanActivityState,
  agent: KanbanOverviewAgent,
  t: TFunction,
): string {
  switch (activity) {
    case "working":
      return t("kanban.working");
    case "done":
      return t("kanban.done");
    case "idle":
      return t("kanban.idle");
    case "waiting":
      return t("kanban.activityWaiting");
    case "blocked":
      return agent.hitl_pending
        ? t("kanban.hitlPending")
        : agent.state === "failed"
        ? formatAgentState(agent.state, t)
        : t("kanban.activityBlocked");
  }
}

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
  const activity = displayActivity(
    agent.activity_state ?? "idle",
    agent.unseen,
  );
  const hasAttention =
    !!agent.hitl_pending || !!agent.pending_plan || agent.state === "failed";
  const statusText = activityLabel(activity, agent, t);
  // Avoid repeating the same attention phrase in aria (chip + footer).
  const ariaLabel = [
    agent.name,
    agent.kind === "team" ? t("kanban.teamTag") : null,
    statusText,
    agent.hitl_pending && activity !== "blocked"
      ? t("kanban.hitlPending")
      : null,
    agent.pending_plan && activity !== "waiting"
      ? t("kanban.pendingPlan")
      : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className={styles.card}
      data-status={agent.kanban_status}
      data-unseen={agent.unseen ? "true" : "false"}
      data-activity={activity}
      onClick={() => onOpen(agent)}
      role="button"
      tabIndex={0}
      aria-label={ariaLabel}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(agent);
        }
      }}
    >
      {hasAttention ? (
        <div className={styles.labels}>
          {agent.hitl_pending ? (
            <span className={`${styles.label} ${styles.labelHitl}`}>
              {t("kanban.hitlPending")}
              {agent.hitl_pending.count > 1
                ? ` ×${agent.hitl_pending.count}`
                : ""}
            </span>
          ) : null}
          {/* Plan wait is already the footer activity label — skip duplicate chip. */}
          {agent.pending_plan && activity !== "waiting" ? (
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
            className={
              activity === "working" ? styles.stateDotSpin : styles.stateDot
            }
            data-activity={activity}
          />
          {statusText}
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
      const silent = opts?.silent ?? false;
      if (!silent) setRefreshing(true);
      try {
        setAgents(await octopAgentsApi.overview());
      } catch (err) {
        // Background polls should stay quiet — toast only on user-initiated loads.
        if (!silent) {
          message.error(apiErrorMessage(err, t("kanban.loadFailed"), t));
        }
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
      // Clear unread immediately so returning to the board does not keep
      // the card in 已完成 after the user has opened the conversation.
      void octopAgentsApi.markRead(agent.agent_id).catch(() => {});
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

  const hasAgents = (agents ?? []).length > 0;
  const hasFilter = search.trim().length > 0 || kindFilter !== "all";
  const filterEmpty = hasAgents && filtered.length === 0 && hasFilter;

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
            prefix={<Search size={14} aria-hidden />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("kanban.searchPlaceholder")}
            aria-label={t("kanban.searchPlaceholder")}
          />
          <Select<KindFilter>
            value={kindFilter}
            onChange={setKindFilter}
            className={styles.kindSelect}
            aria-label={t("kanban.filterKind")}
            options={[
              { value: "all", label: t("kanban.filterAll") },
              { value: "expert", label: t("kanban.filterExperts") },
              { value: "team", label: t("kanban.filterTeams") },
            ]}
          />

          <Button
            icon={<RefreshCw size={14} aria-hidden />}
            loading={refreshing && !loading}
            onClick={() => void load()}
          >
            {t("kanban.refresh")}
          </Button>
        </div>
      }
    >
      {loading ? (
        <CardSkeleton count={4} />
      ) : !hasAgents ? (
        <EmptyState
          variant="mascot"
          title={t("kanban.emptyTitle")}
          description={t("kanban.emptyDescription")}
          actionLabel={t("kanban.emptyAction")}
          onAction={() => navigate("/experts")}
        />
      ) : filterEmpty ? (
        <EmptyState
          title={t("kanban.noMatchesTitle")}
          description={t("kanban.noMatchesDescription")}
          actionLabel={t("kanban.clearFilters")}
          onAction={() => {
            setSearch("");
            setKindFilter("all");
          }}
        />
      ) : (
        <div className={styles.board}>
          {columns.map((col) => (
            <section
              key={col.status}
              className={styles.column}
              data-status={col.status}
              aria-label={`${t(col.labelKey)}, ${col.cards.length}`}
            >
              <div className={styles.columnHeader}>
                <span className={styles.columnDot} aria-hidden />
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
            </section>
          ))}
        </div>
      )}
    </PageShell>
  );
}
