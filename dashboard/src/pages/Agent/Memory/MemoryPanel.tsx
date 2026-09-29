/**
 * Embeddable memory dashboard (tabs + content). Used by the Memory page,
 * Experts MemoryCatalogDrawer, and Personalization.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Empty, Segmented, Select, Tabs } from "antd";
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  Heart,
  Inbox,
  LayoutDashboard,
  MessageSquare,
  Network,
  ScrollText,
  Settings,
  User,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import TabLabel from "../../../components/TabLabel";

import ConversationRecords from "./ConversationRecords";
import Overview from "./Overview";
import ProfileOverview from "./ProfileOverview";
import AtomsList from "./AtomsList";
import RawEventsList from "./RawEventsList";
import EpisodesList from "./EpisodesList";
import JournalList from "./JournalList";
import CandidatesReview from "./CandidatesReview";
import MemoryTree from "./MemoryTree";
import ProactiveConfig from "./ProactiveConfig";
import MemorySettings from "./MemorySettings";

import memoryDashboardApi from "../../../api/modules/memoryDashboard";
import { projectsApi, type ProjectOut } from "../../../api/modules/projects";
import ScopedMemoryView from "./ScopedMemoryView";
import type { MemorySourceLayer } from "./memoryScopes";
import styles from "./index.module.less";

type MemoryTab =
  | "overview"
  | "profile"
  | "library"
  | "episodes"
  | "candidates"
  | "journal"
  | "conversations"
  | "proactive"
  | "settings";

type LibraryView = "tree" | "atoms" | "raw";

/**
 * T-38 — which namespace layer the library shows. ``agent`` is the default so the
 * pre-existing tree/atoms/raw behaviour is untouched; ``team`` and ``project``
 * are the read-only "scope" views (no write affordance — SPEC B38).
 */
type ScopeLayer = MemorySourceLayer;

interface TabDef {
  key: MemoryTab;
  labelKey: string;
  fallback: string;
  icon: LucideIcon;
  showPendingBadge?: boolean;
}

const TABS: TabDef[] = [
  {
    key: "overview",
    labelKey: "memory.tabs.overview",
    fallback: "概览",
    icon: LayoutDashboard,
  },
  {
    key: "profile",
    labelKey: "memory.tabs.profile",
    fallback: "用户画像",
    icon: User,
  },
  {
    key: "library",
    labelKey: "memory.tabs.library",
    fallback: "记忆树",
    icon: Network,
  },
  {
    key: "episodes",
    labelKey: "memory.tabs.episodes",
    fallback: "情绪日记",
    icon: Heart,
  },
  {
    key: "candidates",
    labelKey: "memory.tabs.candidates",
    fallback: "记忆沉淀",
    showPendingBadge: true,
    icon: Inbox,
  },
  {
    key: "journal",
    labelKey: "memory.tabs.journal",
    fallback: "整理记录",
    icon: ScrollText,
  },
  {
    key: "conversations",
    labelKey: "memory.conversationHistory",
    fallback: "对话记录",
    icon: MessageSquare,
  },
  {
    key: "proactive",
    labelKey: "memory.tabs.proactive",
    fallback: "主动关心",
    icon: Bell,
  },
  {
    key: "settings",
    labelKey: "memory.tabs.settings",
    fallback: "设置",
    icon: Settings,
  },
];

export interface MemoryPanelProps {
  agentId: string | null;
  /** Stretch tabs to fill parent height (desktop PageShell / drawer). */
  fill?: boolean;
}

export default function MemoryPanel({
  agentId,
  fill = true,
}: MemoryPanelProps) {
  const { t } = useTranslation();

  const [activeTab, setActiveTab] = useState<MemoryTab>("overview");
  const [libraryView, setLibraryView] = useState<LibraryView>("tree");
  const [scope, setScope] = useState<ScopeLayer>("agent");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  // T-50 「记到项目」: the host owns the write. `scopeReloadKey` re-runs the scope
  // view's read after a successful move, so the row shows up under 项目层.
  const [scopeReloadKey, setScopeReloadKey] = useState(0);
  const [recordHint, setRecordHint] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [expandEntityId, setExpandEntityId] = useState<string | undefined>(
    undefined,
  );
  const [expandKey, setExpandKey] = useState(0);

  useEffect(() => {
    if (!agentId) {
      setPendingCount(0);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const c = await memoryDashboardApi.statsCounts(agentId);
        if (!cancelled) setPendingCount(c.candidates_pending ?? 0);
      } catch {
        if (!cancelled) setPendingCount(0);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId, activeTab]);

  // Projects are only needed once the user switches to the 项目 scope, so the
  // list is fetched lazily and a failure leaves the other scopes working.
  useEffect(() => {
    if (scope !== "project" || projects.length > 0) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await projectsApi.list();
        if (!cancelled) setProjects(list);
      } catch {
        if (!cancelled) setProjects([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scope, projects.length]);

  const tabItems = useMemo(() => {
    if (!agentId) return [];

    const library = (
      <div>
        {/* T-38 — read-only namespace scope. The default `agent` leaves the
            existing tree/atoms/raw behaviour exactly as it was; the other two
            values swap in the scoped, layer-labelled read-only view. */}
        <div className={styles.librarySwitchRow}>
          <Segmented
            value={scope}
            onChange={(v) => setScope(v as ScopeLayer)}
            options={[
              {
                label: t("memory.scope.agentLayer", "我的记忆"),
                value: "agent",
              },
              { label: t("memory.scope.teamLayer", "团队"), value: "team" },
              {
                label: t("memory.scope.projectLayer", "项目"),
                value: "project",
              },
            ]}
          />
          {scope === "agent" ? (
            <Segmented
              value={libraryView}
              onChange={(v) => setLibraryView(v as LibraryView)}
              options={[
                {
                  label: t("memory.library.viewTree", "主题视图"),
                  value: "tree",
                },
                {
                  label: t("memory.library.viewAtoms", "列表视图"),
                  value: "atoms",
                },
                {
                  label: t("memory.library.viewRaw", "原始素材"),
                  value: "raw",
                },
              ]}
            />
          ) : null}
          {scope === "project" ? (
            <Select
              value={projectId ?? undefined}
              onChange={(v) => setProjectId(v ?? null)}
              placeholder={t("memory.scope.pickProject", "选择项目")}
              style={{ minWidth: 200 }}
              showSearch
              optionFilterProp="label"
              allowClear
              data-testid="memory-scope-project-select"
              options={projects.map((p) => ({
                label: p.name,
                value: p.project_id,
              }))}
            />
          ) : null}
          <span className={styles.librarySwitchHint}>
            {scope !== "agent"
              ? t(
                  "memory.scope.hintScoped",
                  "按命名空间层只读浏览：项目层 → 团队层 → agent 私有层",
                )
              : libraryView === "tree"
              ? t(
                  "memory.library.hintTree",
                  "按人、项目、工具等主题，分组浏览相关记忆",
                )
              : libraryView === "atoms"
              ? t(
                  "memory.library.hintAtoms",
                  "扁平展示全部记忆，可按重要程度筛选",
                )
              : t(
                  "memory.library.hintRaw",
                  "提炼前捕获的原始对话记忆（条数与「对话记录」不一一对应）",
                )}
          </span>
        </div>
        {scope !== "agent" ? (
          <ScopedMemoryView
            agentId={agentId}
            scope={scope}
            projectId={projectId}
            reloadKey={scopeReloadKey}
            onRecordToProject={
              scope === "project" && projectId
                ? (item) => {
                    setRecordHint(null);
                    void memoryDashboardApi
                      .recordAtomToProject(agentId, item.id, projectId)
                      .then(() => setScopeReloadKey((k) => k + 1))
                      .catch((err: unknown) =>
                        setRecordHint(
                          err instanceof Error ? err.message : String(err),
                        ),
                      );
                  }
                : undefined
            }
            recordToProjectHint={
              scope === "project" && projectId
                ? recordHint ??
                  t(
                    "memory.scope.recordToProjectHint",
                    "写入项目层需要该项目的写入权限：读得出不等于写得进。",
                  )
                : null
            }
          />
        ) : libraryView === "tree" ? (
          <MemoryTree
            key={expandKey}
            agentId={agentId}
            initialExpandEntityId={expandEntityId}
          />
        ) : libraryView === "atoms" ? (
          <AtomsList agentId={agentId} />
        ) : (
          <RawEventsList agentId={agentId} />
        )}
      </div>
    );

    return TABS.map((tab) => {
      const showBadge = tab.showPendingBadge && pendingCount > 0;
      const label = (
        <TabLabel icon={tab.icon}>
          {t(tab.labelKey, tab.fallback)}
          {showBadge ? (
            <span className={styles.tabBadge}>{pendingCount}</span>
          ) : null}
        </TabLabel>
      );

      let children: ReactNode = null;
      switch (tab.key) {
        case "overview":
          children = (
            <Overview
              agentId={agentId}
              onViewConversations={() => setActiveTab("conversations")}
              onReviewCandidates={() => setActiveTab("candidates")}
              onOpenSettings={() => setActiveTab("settings")}
            />
          );
          break;
        case "profile":
          children = (
            <ProfileOverview
              agentId={agentId}
              onReview={() => setActiveTab("candidates")}
              onViewAll={(entityId) => {
                setExpandEntityId(entityId);
                setExpandKey((k) => k + 1);
                setLibraryView("tree");
                setActiveTab("library");
              }}
            />
          );
          break;
        case "library":
          children = library;
          break;
        case "episodes":
          children = <EpisodesList agentId={agentId} />;
          break;
        case "candidates":
          // T-50: the host owns the project-directed write. The reusable project
          // list already loaded for the scope switcher is the 「归属项目」 menu, and
          // the request goes through the single network exit (no fetch here).
          children = (
            <CandidatesReview
              agentId={agentId}
              projects={projects.map((p) => ({
                id: p.project_id,
                name: p.name,
              }))}
              onPromoteToProject={async (candidate, projectId) => {
                await memoryDashboardApi.promoteCandidateToProject(
                  agentId,
                  candidate.id,
                  projectId,
                );
              }}
            />
          );
          break;
        case "journal":
          children = <JournalList agentId={agentId} />;
          break;
        case "conversations":
          children = <ConversationRecords agentId={agentId} />;
          break;
        case "proactive":
          children = (
            <ProactiveConfig
              agentId={agentId}
              onSwitchToEpisodes={() => setActiveTab("episodes")}
            />
          );
          break;
        case "settings":
          children = <MemorySettings agentId={agentId} />;
          break;
      }

      return { key: tab.key, label, children };
    });
  }, [
    agentId,
    expandEntityId,
    expandKey,
    libraryView,
    pendingCount,
    projectId,
    projects,
    scope,
    t,
  ]);

  if (!agentId) {
    return (
      <Empty
        description={t("memory.noAgentSelected")}
        style={{ marginTop: 64 }}
      />
    );
  }

  return (
    <Tabs
      className={styles.memoryTabs}
      style={fill ? undefined : { height: "auto" }}
      activeKey={activeTab}
      onChange={(k) => setActiveTab(k as MemoryTab)}
      destroyOnHidden
      items={tabItems}
    />
  );
}
