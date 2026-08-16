import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Empty } from "antd";
import { Bot, Brain, Notebook, Sparkles, Waypoints } from "lucide-react";
import PageShell, { pageShellStyles } from "../../../layouts/PageShell";
import { useAgent } from "../../../context/AgentContext";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { usePathTabs } from "../../../hooks/usePathTabs";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { userCan } from "../../../utils/permissions";
import SkillsTabs from "../Skills/components/SkillsTabs";
import SubagentManager from "../../Experts/components/SubagentManager";
import MBTISelector from "./components/MBTISelector";
import MemoryPanel from "../Memory/MemoryPanel";
import ChannelsPanel from "../Channels/ChannelsPanel";
import styles from "./index.module.less";

export type PersonalizationTab =
  | "skills"
  | "subagents"
  | "mbti"
  | "memory"
  | "channels";

const PERSONALIZATION_TABS = [
  "skills",
  "subagents",
  "mbti",
  "memory",
  "channels",
] as const satisfies readonly PersonalizationTab[];

const TAB_ICONS = {
  skills: Sparkles,
  subagents: Bot,
  mbti: Brain,
  memory: Notebook,
  channels: Waypoints,
} as const;

export default function PersonalizationPage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const user = useCurrentUser();
  const { activeAgentId, agents } = useAgent();
  const activeAgent = agents.find((a) => a.agent_id === activeAgentId);
  const isAllowed = useCallback(
    (tab: PersonalizationTab) =>
      tab !== "channels" || userCan(user, "channels"),
    [user],
  );

  const { activeTab, handleTabChange, isMounted } = usePathTabs({
    basePath: "/personalization",
    tabs: PERSONALIZATION_TABS,
    storageKey: "octop:personalization:tab",
    defaultTab: "skills",
    isAllowed,
  });

  const pathTabs = useMemo(
    () => ({
      value: activeTab,
      onChange: handleTabChange,
      options: PERSONALIZATION_TABS.filter((value) => isAllowed(value)).map(
        (value) => {
          const Icon = TAB_ICONS[value];
          return {
            value,
            label: t(`personalization.tabs.${value}`),
            icon: <Icon size={14} strokeWidth={2} />,
          };
        },
      ),
    }),
    [activeTab, handleTabChange, isAllowed, t],
  );

  const pageTitle = `${t("personalization.title")} / ${t(
    `personalization.tabs.${activeTab}`,
  )}`;

  return (
    <PageShell
      title={pageTitle}
      subtitle={t("personalization.description")}
      agentScoped
      fill={!isMobile}
      pathTabs={pathTabs}
    >
      <div className={styles.panels}>
        {isMounted("skills") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "skills" ? "flex" : "none" }}
            aria-hidden={activeTab !== "skills"}
          >
            <div className={pageShellStyles.fillChild}>
              <SkillsTabs agentId={activeAgentId} />
            </div>
          </div>
        )}

        {isMounted("subagents") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "subagents" ? "flex" : "none" }}
            aria-hidden={activeTab !== "subagents"}
          >
            {!activeAgentId ? (
              <Empty
                style={{ marginTop: isMobile ? 48 : 24 }}
                description={t("subagents.pickAgent")}
              />
            ) : (
              <SubagentManager
                key={activeAgentId}
                agentId={activeAgentId}
                agentState={activeAgent?.state ?? "stopped"}
                fillHeight={isMobile}
              />
            )}
          </div>
        )}

        {isMounted("mbti") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "mbti" ? "flex" : "none" }}
            aria-hidden={activeTab !== "mbti"}
          >
            {!activeAgentId ? (
              <Empty
                style={{ marginTop: 24 }}
                description={t("mbtiPage.pickAgent")}
              />
            ) : (
              <div className={pageShellStyles.fillChild}>
                <MBTISelector
                  key={activeAgentId}
                  showHeader={false}
                  showTestAction
                />
              </div>
            )}
          </div>
        )}

        {isMounted("memory") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "memory" ? "flex" : "none" }}
            aria-hidden={activeTab !== "memory"}
          >
            {isMobile ? (
              <MemoryPanel agentId={activeAgentId} fill={false} />
            ) : (
              <div className={pageShellStyles.fillChild}>
                <MemoryPanel agentId={activeAgentId} fill />
              </div>
            )}
          </div>
        )}

        {isMounted("channels") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "channels" ? "flex" : "none" }}
            aria-hidden={activeTab !== "channels"}
          >
            <div className={pageShellStyles.fillChild}>
              <ChannelsPanel agentId={activeAgentId} />
            </div>
          </div>
        )}
      </div>
    </PageShell>
  );
}
