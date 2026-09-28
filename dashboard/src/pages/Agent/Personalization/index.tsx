import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button, Empty } from "antd";
import {
  Bot,
  Brain,
  Notebook,
  Puzzle,
  Sparkles,
  Waypoints,
  Wrench,
} from "lucide-react";
import PageShell, { pageShellStyles } from "../../../layouts/PageShell";
import { useAgent } from "../../../context/AgentContext";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { usePathTabs } from "../../../hooks/usePathTabs";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { userCan } from "../../../utils/permissions";
import { ownedSoloExperts } from "../../../utils/sharedExpert";
import SkillsTabs from "../Skills/components/SkillsTabs";
import ToolsTabs from "../Tools/ToolsTabs";
import SubagentManager from "../../Experts/components/SubagentManager";
import MBTISelector from "./components/MBTISelector";
import AgentPluginsPanel from "./components/AgentPluginsPanel";
import MemoryPanel from "../Memory/MemoryPanel";
import ChannelsPanel from "../Channels/ChannelsPanel";
import styles from "./index.module.less";

export type PersonalizationTab =
  | "skills"
  | "subagents"
  | "tools"
  | "plugins"
  | "mbti"
  | "memory"
  | "channels";

const PERSONALIZATION_TABS = [
  "skills",
  "subagents",
  "tools",
  "plugins",
  "mbti",
  "memory",
  "channels",
] as const satisfies readonly PersonalizationTab[];

const TAB_ICONS = {
  skills: Sparkles,
  subagents: Bot,
  tools: Wrench,
  plugins: Puzzle,
  mbti: Brain,
  memory: Notebook,
  channels: Waypoints,
} as const;

export default function PersonalizationPage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const user = useCurrentUser();
  const { activeAgentId, agents, loading } = useAgent();
  // Personalization edits the selected expert, so it must be one the user
  // owns. The agent list puts other users' shared experts first, and the
  // agent bar only corrects the selection when the user owns an expert, so a
  // new account would otherwise browse and edit someone else's (#1097).
  const ownedAgents = useMemo(() => ownedSoloExperts(agents), [agents]);
  const activeAgent = ownedAgents.find((a) => a.agent_id === activeAgentId);
  const agentId = activeAgent?.agent_id ?? null;
  const isAllowed = useCallback(
    (tab: PersonalizationTab) => {
      if (tab === "channels") return userCan(user, "channels");
      return true;
    },
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

  if (!loading && ownedAgents.length === 0) {
    return (
      <PageShell
        title={pageTitle}
        subtitle={t("personalization.description")}
        agentScoped
        pathTabs={pathTabs}
      >
        <Empty
          style={{ marginTop: isMobile ? 48 : 24 }}
          description={
            <>
              <div>{t("chat.noAgentsTitle")}</div>
              <div>{t("chat.noAgentsHint")}</div>
            </>
          }
        >
          <Button type="primary" onClick={() => navigate("/experts")}>
            {t("chat.createExpert")}
          </Button>
        </Empty>
      </PageShell>
    );
  }

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
              <SkillsTabs agentId={agentId} />
            </div>
          </div>
        )}

        {isMounted("tools") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "tools" ? "flex" : "none" }}
            aria-hidden={activeTab !== "tools"}
          >
            <div className={pageShellStyles.fillChild}>
              <ToolsTabs agentId={agentId} />
            </div>
          </div>
        )}

        {isMounted("plugins") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "plugins" ? "flex" : "none" }}
            aria-hidden={activeTab !== "plugins"}
          >
            <div className={pageShellStyles.fillChild}>
              <AgentPluginsPanel agentId={agentId} />
            </div>
          </div>
        )}

        {isMounted("subagents") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "subagents" ? "flex" : "none" }}
            aria-hidden={activeTab !== "subagents"}
          >
            {!agentId ? (
              <Empty
                style={{ marginTop: isMobile ? 48 : 24 }}
                description={t("subagents.pickAgent")}
              />
            ) : (
              <SubagentManager
                key={agentId}
                agentId={agentId}
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
            {!agentId ? (
              <Empty
                style={{ marginTop: 24 }}
                description={t("mbtiPage.pickAgent")}
              />
            ) : (
              <div className={pageShellStyles.fillChild}>
                <MBTISelector
                  key={agentId}
                  agentId={agentId}
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
              <MemoryPanel agentId={agentId} fill={false} />
            ) : (
              <div className={pageShellStyles.fillChild}>
                <MemoryPanel agentId={agentId} fill />
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
              <ChannelsPanel agentId={agentId} />
            </div>
          </div>
        )}
      </div>
    </PageShell>
  );
}
