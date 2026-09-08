/**
 * SkillsTabs — the full three-tab skills surface (已安装 / 内置 / 技能市场):
 *   1. Customized Skills  (workspace kind, editable + deletable)
 *   2. Built-in Skills    (builtin kind, toggle only)
 *   3. Skill Market       (SkillHub marketplace)
 *
 * Extracted from the Skills page so it can be embedded both on the dedicated
 * `/skills` route and inside drawers (e.g. the expert skill catalog). It takes
 * an explicit `agentId` so callers decide which agent's skills to show.
 */

import { useState } from "react";
import { Empty } from "antd";
import { Blocks, Package, Sparkles, Store } from "lucide-react";
import { useTranslation } from "react-i18next";
import TabBar, {
  type TabBarItem,
} from "../../../../components/TabLabel/TabBar";
import InstalledSkillsTab from "./InstalledSkillsTab";
import SkillPackagesTab from "./SkillPackagesTab";
import SkillHubTab from "./SkillHubTab";
import { useSkills } from "../useSkills";
import styles from "../index.module.less";

type SkillsTab = "custom" | "builtin" | "skillhub" | "packages";

const SKILL_TABS: TabBarItem<SkillsTab>[] = [
  { key: "custom", labelKey: "skills.customizedSkills", icon: Sparkles },
  { key: "builtin", labelKey: "skills.builtinSkills", icon: Blocks },
  { key: "skillhub", labelKey: "skills.tencentSkillHub", icon: Store },
  { key: "packages", labelKey: "skills.skillPackages", icon: Package },
];

interface SkillsTabsProps {
  /** Agent whose skills are shown. */
  agentId: string | null;
}

export default function SkillsTabs({ agentId }: SkillsTabsProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<SkillsTab>("custom");
  const onInstalledTab =
    activeTab === "custom" ||
    activeTab === "builtin" ||
    activeTab === "packages";
  const installedSkills = useSkills(agentId, { enabled: onInstalledTab });

  const noAgent = (
    <Empty
      description={t("skills.noAgentSelected")}
      style={{ marginTop: 64 }}
    />
  );

  return (
    <div className={styles.skillsTabs}>
      <TabBar tabs={SKILL_TABS} activeKey={activeTab} onChange={setActiveTab} />

      <div className={styles.skillsTabsContent}>
        {activeTab === "custom" || activeTab === "builtin" ? (
          agentId ? (
            <InstalledSkillsTab
              key={agentId}
              agentId={agentId}
              kind={activeTab === "builtin" ? "builtin" : "custom"}
              {...installedSkills}
            />
          ) : (
            noAgent
          )
        ) : activeTab === "skillhub" && agentId ? (
          <SkillHubTab key={agentId} target={{ type: "agent", agentId }} />
        ) : activeTab === "packages" && agentId ? (
          <SkillPackagesTab
            key={agentId}
            agentId={agentId}
            skills={installedSkills.skills}
            fetchSkills={installedSkills.fetchSkills}
            toggleEnabled={installedSkills.toggleEnabled}
          />
        ) : (
          noAgent
        )}
      </div>
    </div>
  );
}
