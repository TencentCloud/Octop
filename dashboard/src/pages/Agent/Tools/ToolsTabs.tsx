/**
 * ToolsTabs — three-tab tools surface for Personalization:
 *   1. Built-in tools
 *   2. Plugin tools
 *   3. ACP tools (admin only)
 */

import { useMemo, useState } from "react";
import { Puzzle, Share2, Wrench } from "lucide-react";
import TabBar, { type TabBarItem } from "../../../components/TabLabel/TabBar";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { canAccessKeys } from "../../../utils/permissions";
import { ACPPanel } from "../ACP";
import ToolsPanel from "./ToolsPanel";
import styles from "./ToolsTabs.module.less";

type ToolsTab = "builtin" | "plugin" | "acp";

const TOOL_TABS: TabBarItem<ToolsTab>[] = [
  { key: "builtin", labelKey: "toolSettings.tabs.builtin", icon: Wrench },
  { key: "plugin", labelKey: "toolSettings.tabs.plugin", icon: Puzzle },
  { key: "acp", labelKey: "toolSettings.tabs.acp", icon: Share2 },
];

interface ToolsTabsProps {
  agentId: string | null;
}

export default function ToolsTabs({ agentId }: ToolsTabsProps) {
  const user = useCurrentUser();
  const canAcp = canAccessKeys(user, "admin");
  const [activeTab, setActiveTab] = useState<ToolsTab>("builtin");

  const tabs = useMemo(
    () => TOOL_TABS.filter((tab) => tab.key !== "acp" || canAcp),
    [canAcp],
  );

  const resolvedTab = activeTab === "acp" && !canAcp ? "builtin" : activeTab;

  return (
    <div className={styles.toolsTabs}>
      <TabBar tabs={tabs} activeKey={resolvedTab} onChange={setActiveTab} />

      <div
        className={`${styles.toolsTabsContent}${
          resolvedTab === "acp" ? ` ${styles.toolsTabsContentPadded}` : ""
        }`}
      >
        {resolvedTab === "builtin" ? (
          <ToolsPanel agentId={agentId} source="builtin" />
        ) : resolvedTab === "plugin" ? (
          <ToolsPanel agentId={agentId} source="plugin" />
        ) : (
          <ACPPanel />
        )}
      </div>
    </div>
  );
}
