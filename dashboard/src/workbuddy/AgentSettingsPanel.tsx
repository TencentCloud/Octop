import { Empty } from "antd";
import { useTranslation } from "react-i18next";
import { useAgent } from "../context/AgentContext";
import MemoryPanel from "../pages/Agent/Memory/MemoryPanel";
import ChannelsPanel from "../pages/Agent/Channels/ChannelsPanel";
import ToolsTabs from "../pages/Agent/Tools/ToolsTabs";
import MBTISelector from "../pages/Agent/Personalization/components/MBTISelector";
import AgentPluginsPanel from "../pages/Agent/Personalization/components/AgentPluginsPanel";
import SubagentManager from "../pages/Experts/components/SubagentManager";
import Config from "../pages/Agent/Config";
export default function AgentSettingsPanel({ panel }: { panel: string }) {
  const { t } = useTranslation();
  const { activeAgentId, activeAgent } = useAgent();
  if (!activeAgentId)
    return <Empty description={t("skills.noAgentSelected")} />;
  switch (panel) {
    case "memory":
      return <MemoryPanel agentId={activeAgentId} />;
    case "channels":
      return <ChannelsPanel agentId={activeAgentId} />;
    case "tools":
      return <ToolsTabs agentId={activeAgentId} />;
    case "plugins":
      return <AgentPluginsPanel agentId={activeAgentId} />;
    case "subagents":
      return (
        <SubagentManager
          agentId={activeAgentId}
          agentState={activeAgent?.state ?? "stopped"}
        />
      );
    case "config":
      return <Config />;
    default:
      return <MBTISelector showHeader={false} showTestAction />;
  }
}
