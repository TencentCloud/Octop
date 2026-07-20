/**
 * Memory — per-agent memory dashboard.
 *
 * Episodes are intentionally isolated from normal conversational recall and
 * shown as the emotional-diary tab for proactive care and summaries.
 * The memory library is a single user-facing surface with tree and list views;
 * pending candidates keep a badge on the review tab.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Empty, Segmented, Tabs } from "antd";
import { useTranslation } from "react-i18next";

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

import PageShell from "../../../layouts/PageShell";
import { useAgent } from "../../../context/AgentContext";
import memoryDashboardApi from "../../../api/modules/memoryDashboard";
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

/** Internal view for the memory-library tab. */
type LibraryView = "tree" | "atoms" | "raw";

interface TabDef {
  key: MemoryTab;
  labelKey: string;
  fallback: string;
  /** Whether to show the pending-memory badge. */
  showPendingBadge?: boolean;
}

// Tab order: overview -> profile -> library -> episodes -> candidates -> journal -> conversations -> proactive care.
const TABS: TabDef[] = [
  { key: "overview", labelKey: "memory.tabs.overview", fallback: "概览" },
  { key: "profile", labelKey: "memory.tabs.profile", fallback: "用户画像" },
  { key: "library", labelKey: "memory.tabs.library", fallback: "记忆树" },
  { key: "episodes", labelKey: "memory.tabs.episodes", fallback: "情绪日记" },
  {
    key: "candidates",
    labelKey: "memory.tabs.candidates",
    fallback: "全部",
    showPendingBadge: true,
  },
  { key: "journal", labelKey: "memory.tabs.journal", fallback: "整理记录" },
  {
    key: "conversations",
    labelKey: "memory.conversationHistory",
    fallback: "对话记录",
  },
  { key: "proactive", labelKey: "memory.tabs.proactive", fallback: "主动关心" },
  { key: "settings", labelKey: "memory.tabs.settings", fallback: "设置" },
];

export default function MemoryPage() {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();

  const [activeTab, setActiveTab] = useState<MemoryTab>("overview");
  const [libraryView, setLibraryView] = useState<LibraryView>("tree");
  const [pendingCount, setPendingCount] = useState(0);
  const [expandEntityId, setExpandEntityId] = useState<string | undefined>(
    undefined,
  );
  // Increment on profile-page jumps to force MemoryTree remounts, even for the same entityId.
  const [expandKey, setExpandKey] = useState(0);

  // Fetch candidates_pending for the review-tab badge.
  useEffect(() => {
    if (!activeAgentId) {
      setPendingCount(0);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const c = await memoryDashboardApi.statsCounts(activeAgentId);
        if (!cancelled) setPendingCount(c.candidates_pending ?? 0);
      } catch {
        if (!cancelled) setPendingCount(0);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeAgentId, activeTab]);

  const tabItems = useMemo(() => {
    if (!activeAgentId) return [];

    const library = (
      <div>
        <div className={styles.librarySwitchRow}>
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
          <span className={styles.librarySwitchHint}>
            {libraryView === "tree"
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
                  "提炼前捕获的原始对话素材（条数与「对话记录」不一一对应）",
                )}
          </span>
        </div>
        {libraryView === "tree" ? (
          <MemoryTree
            key={expandKey}
            agentId={activeAgentId}
            initialExpandEntityId={expandEntityId}
          />
        ) : libraryView === "atoms" ? (
          <AtomsList agentId={activeAgentId} />
        ) : (
          <RawEventsList agentId={activeAgentId} />
        )}
      </div>
    );

    return TABS.map((tab) => {
      const showBadge = tab.showPendingBadge && pendingCount > 0;
      const label = (
        <span className={styles.tabLabel}>
          {t(tab.labelKey, tab.fallback)}
          {showBadge ? (
            <span className={styles.tabBadge}>{pendingCount}</span>
          ) : null}
        </span>
      );

      let children: ReactNode = null;
      switch (tab.key) {
        case "overview":
          children = (
            <Overview
              agentId={activeAgentId}
              onViewConversations={() => setActiveTab("conversations")}
              onReviewCandidates={() => setActiveTab("candidates")}
              onOpenSettings={() => setActiveTab("settings")}
            />
          );
          break;
        case "profile":
          children = (
            <ProfileOverview
              agentId={activeAgentId}
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
          children = <EpisodesList agentId={activeAgentId} />;
          break;
        case "candidates":
          children = <CandidatesReview agentId={activeAgentId} />;
          break;
        case "journal":
          children = <JournalList agentId={activeAgentId} />;
          break;
        case "conversations":
          children = <ConversationRecords agentId={activeAgentId} />;
          break;
        case "proactive":
          children = (
            <ProactiveConfig
              agentId={activeAgentId}
              onSwitchToEpisodes={() => setActiveTab("episodes")}
            />
          );
          break;
        case "settings":
          children = <MemorySettings agentId={activeAgentId} />;
          break;
      }

      return { key: tab.key, label, children };
    });
  }, [activeAgentId, expandEntityId, expandKey, libraryView, pendingCount, t]);

  if (!activeAgentId) {
    return (
      <PageShell
        title={t("pageShell.memory.title")}
        subtitle={t("pageShell.memory.subtitle")}
        agentScoped
      >
        <Empty
          description={t("memory.noAgentSelected")}
          style={{ marginTop: 64 }}
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      title={t("pageShell.memory.title")}
      subtitle={t("pageShell.memory.subtitle")}
      agentScoped
    >
      <Tabs
        className={styles.memoryTabs}
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as MemoryTab)}
        destroyOnHidden
        items={tabItems}
      />
    </PageShell>
  );
}
