/**
 * Experts page — redesigned as Agents Management Centre.
 *
 * Tab A: user's experts, shown as a card grid with start/stop/edit/delete.
 * Tab B: expert templates, shown as a card grid with create-from-template drawer.
 *
 * API (all via request() which already prefixes /api):
 *   GET  /experts                         → ExpertSummary[]
 *   GET  /agents                          → via AgentContext
 *   POST /agents/from-expert/{id}         → create agent (via CreateFromExpertDrawer)
 *   POST /agents/{id}/start|stop          → lifecycle (via AgentCard)
 *   PATCH /agents/{id}                    → edit (via EditAgentDrawer)
 *   DELETE /agents/{id}                   → delete (via AgentCard)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Spin, Tabs, Segmented, Tooltip, message } from "antd";
import { GraduationCap, LayoutGrid, List, RefreshCw } from "lucide-react";
import PageShell from "../../layouts/PageShell";
import { request } from "../../api/request";
import { useAgent } from "../../context/AgentContext";
import { useCardTableView } from "../../hooks/useCardTableView";
import type { OctopAgent } from "../../context/AgentContext";
import { AgentCard } from "./components/AgentCard";
import { ExpertCard } from "./components/ExpertCard";
import type { ExpertSummary } from "./components/ExpertCard";
import EditAgentDrawer from "./components/EditAgentDrawer";
import CreateFromExpertDrawer from "./components/CreateFromExpertDrawer";
import AgentExpertsTable from "./components/AgentExpertsTable";
import styles from "./index.module.less";

type TabKey = "my" | "library";
type ViewMode = "card" | "table";
const VIEW_STORAGE_KEY = "octop:experts-view";

function loadViewMode(): ViewMode {
  const stored = localStorage.getItem(VIEW_STORAGE_KEY);
  return stored === "table" ? "table" : "card";
}

async function fetchExpertLibrary(): Promise<ExpertSummary[]> {
  return request<ExpertSummary[]>("/experts");
}

async function fetchInstalledExpertIds(): Promise<Set<string>> {
  const data = await request<{ config?: { expert_id?: string } }[]>("/agents");
  return new Set(
    data.flatMap((a) => (a.config?.expert_id ? [a.config.expert_id] : [])),
  );
}

export default function ExpertsPage() {
  const { t, i18n } = useTranslation();
  const lang: "zh" | "en" = i18n.language?.startsWith("zh") ? "zh" : "en";
  const { agents, refresh: refreshAgents } = useAgent();

  // ── Tab state ──────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<TabKey>("my");
  const { viewMode, setViewMode, showCardView } = useCardTableView(
    loadViewMode(),
  );
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [agentList, expertList, installedIds] = await Promise.all([
        request<OctopAgent[]>("/agents"),
        fetchExpertLibrary(),
        fetchInstalledExpertIds(),
      ]);
      setLocalAgents(agentList);
      setExperts(expertList);
      setAgentExpertIds(installedIds);
      await refreshAgents({ silent: true, force: true });
    } catch (err: unknown) {
      message.error(
        err instanceof Error ? err.message : t("experts.loadFailed"),
      );
    } finally {
      setRefreshing(false);
    }
  }, [refreshAgents, t]);

  const onViewChange = (value: string | number) => {
    const mode = value === "table" ? "table" : "card";
    setViewMode(mode);
    localStorage.setItem(VIEW_STORAGE_KEY, mode);
  };

  // ── Expert library ─────────────────────────────────────────────
  const [experts, setExperts] = useState<ExpertSummary[]>([]);
  const [expertLoading, setExpertLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setExpertLoading(true);
    fetchExpertLibrary()
      .then((data) => {
        if (!cancelled) setExperts(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        message.error(
          err instanceof Error ? err.message : t("experts.loadFailed"),
        );
      })
      .finally(() => {
        if (!cancelled) setExpertLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  // ── Local agent state (extends AgentContext for optimistic updates) ──
  const [localAgents, setLocalAgents] = useState<OctopAgent[]>(agents);
  const [newAgentId, setNewAgentId] = useState<string | null>(null);

  useEffect(() => {
    setLocalAgents(agents);
  }, [agents]);

  const handleStateChange = useCallback((agentId: string, newState: string) => {
    setLocalAgents((prev) =>
      prev.map((a) => (a.agent_id === agentId ? { ...a, state: newState } : a)),
    );
  }, []);

  const handleDeleted = (agentId: string) => {
    setLocalAgents((prev) => prev.filter((a) => a.agent_id !== agentId));
    void refreshAgents();
  };

  // ── Edit Drawer ────────────────────────────────────────────────
  const [editAgent, setEditAgent] = useState<OctopAgent | null>(null);

  const handleEditSaved = useCallback(
    (
      updated: Pick<
        OctopAgent,
        "agent_id" | "name" | "description" | "default_model"
      >,
    ) => {
      setEditAgent(null);
      setLocalAgents((prev) =>
        prev.map((a) =>
          a.agent_id === updated.agent_id
            ? {
                ...a,
                name: updated.name,
                description: updated.description,
                default_model: updated.default_model,
              }
            : a,
        ),
      );
      void refreshAgents({ silent: true });
    },
    [refreshAgents],
  );

  // ── Create-from-expert Drawer ──────────────────────────────────
  const [createExpert, setCreateExpert] = useState<ExpertSummary | null>(null);

  const handleCreated = (agentId: string) => {
    setCreateExpert(null);
    void refreshAgents({ silent: true });
    setActiveTab("my");
    setNewAgentId(agentId);
    setTimeout(() => setNewAgentId(null), 1000);
  };

  const openExpertLibrary = useCallback(() => {
    setActiveTab("library");
  }, []);

  // ── "Installed" badge lookup ───────────────────────────────────
  const [agentExpertIds, setAgentExpertIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (activeTab !== "library") return;
    let cancelled = false;
    fetchInstalledExpertIds()
      .then((ids) => {
        if (!cancelled) setAgentExpertIds(ids);
      })
      .catch(() => {
        /* non-critical */
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, localAgents.length]);

  const refreshButton = useMemo(
    () => (
      <Tooltip title={t("common.refresh")}>
        <button
          className={styles.toolbarIconBtn}
          onClick={() => void handleRefresh()}
          disabled={refreshing}
          type="button"
        >
          <RefreshCw
            size={14}
            className={refreshing ? styles.spinning : undefined}
          />
        </button>
      </Tooltip>
    ),
    [handleRefresh, refreshing, t],
  );

  // ── Render helpers ─────────────────────────────────────────────

  const myExpertsContent = useMemo(() => {
    if (localAgents.length === 0) {
      return (
        <div className={styles.emptyState}>
          <GraduationCap
            size={48}
            style={{ color: "var(--fn-text-tertiary)" }}
          />
          <div className={styles.emptyTitle}>{t("experts.emptyMyExperts")}</div>
          <div className={styles.emptyHint}>
            {t("experts.emptyMyExpertsHint")}
          </div>
          <div className={styles.emptyActions}>
            {refreshButton}
            <button className={styles.emptyAction} onClick={openExpertLibrary}>
              {t("experts.goToLibrary")}
            </button>
          </div>
        </div>
      );
    }

    return (
      <>
        <div className={styles.gridToolbar}>
          <span className={styles.gridCount}>
            {t("experts.totalAgents", { count: localAgents.length })}
          </span>
          <div className={styles.gridToolbarRight}>
            <Segmented
              size="small"
              value={viewMode}
              onChange={onViewChange}
              options={[
                {
                  value: "card",
                  label: (
                    <span className={styles.viewModeLabel}>
                      <LayoutGrid size={14} />
                      {t("experts.viewCard", "卡片")}
                    </span>
                  ),
                },
                {
                  value: "table",
                  label: (
                    <span className={styles.viewModeLabel}>
                      <List size={14} />
                      {t("experts.viewTable", "表格")}
                    </span>
                  ),
                },
              ]}
            />
            {refreshButton}
            <button className={styles.toolbarBtn} onClick={openExpertLibrary}>
              {t("experts.addFromLibrary")}
            </button>
          </div>
        </div>
        {showCardView ? (
          <div className={styles.cardGrid}>
            {localAgents.map((agent) => (
              <div
                key={agent.agent_id}
                className={
                  newAgentId === agent.agent_id
                    ? styles.agentCardNew
                    : undefined
                }
              >
                <AgentCard
                  agent={agent}
                  iconName={agent.icon_name}
                  accentColor={agent.color}
                  onEdit={(id) =>
                    setEditAgent(
                      localAgents.find((a) => a.agent_id === id) ?? null,
                    )
                  }
                  onDeleted={handleDeleted}
                  onStateChange={handleStateChange}
                />
              </div>
            ))}
          </div>
        ) : (
          <AgentExpertsTable
            agents={localAgents}
            onEdit={(id) =>
              setEditAgent(localAgents.find((a) => a.agent_id === id) ?? null)
            }
            onDeleted={handleDeleted}
            onStateChange={handleStateChange}
          />
        )}
      </>
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    localAgents,
    newAgentId,
    openExpertLibrary,
    refreshButton,
    showCardView,
    t,
  ]);

  const libraryContent = useMemo(() => {
    if (expertLoading) {
      return (
        <div className={styles.loadingState}>
          <Spin />
        </div>
      );
    }
    if (experts.length === 0) {
      return (
        <div className={styles.emptyState}>
          <GraduationCap
            size={48}
            style={{ color: "var(--fn-text-tertiary)" }}
          />
          <div className={styles.emptyTitle}>{t("experts.emptyLibrary")}</div>
          <div className={styles.emptyHint}>
            {t("experts.emptyLibraryHint")}
          </div>
          <div className={styles.emptyActions}>{refreshButton}</div>
        </div>
      );
    }
    return (
      <>
        <div className={styles.gridToolbar}>
          <span className={styles.gridCount}>
            {t("experts.totalLibrary", { count: experts.length })}
          </span>
          <div className={styles.gridToolbarRight}>{refreshButton}</div>
        </div>
        <div className={styles.cardGrid}>
          {experts.map((expert) => (
            <ExpertCard
              key={expert.id}
              expert={expert}
              lang={lang}
              isInstalled={agentExpertIds.has(expert.id)}
              onCreate={setCreateExpert}
            />
          ))}
        </div>
      </>
    );
  }, [experts, expertLoading, lang, agentExpertIds, refreshButton, t]);

  return (
    <PageShell
      title={t("pageShell.experts.title")}
      subtitle={t("pageShell.experts.subtitle")}
    >
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as TabKey)}
        items={[
          {
            key: "my",
            label: t("experts.myExperts"),
            children: myExpertsContent,
          },
          {
            key: "library",
            label: t("experts.expertLibrary"),
            children: libraryContent,
          },
        ]}
      />

      <EditAgentDrawer
        open={!!editAgent}
        agent={editAgent}
        onClose={() => setEditAgent(null)}
        onSaved={handleEditSaved}
      />

      <CreateFromExpertDrawer
        open={!!createExpert}
        expert={createExpert}
        lang={lang}
        onClose={() => setCreateExpert(null)}
        onCreated={handleCreated}
      />
    </PageShell>
  );
}
