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
import { useTranslation } from "react-i18next";
import InstalledSkillsTab from "./InstalledSkillsTab";
import SkillHubTab from "./SkillHubTab";
import { useSkills } from "../useSkills";
import styles from "../index.module.less";

type SkillsTab = "custom" | "builtin" | "skillhub";

interface SkillsTabsProps {
  /** Agent whose skills are shown. */
  agentId: string | null;
}

export default function SkillsTabs({ agentId }: SkillsTabsProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<SkillsTab>("custom");
  const onInstalledTab = activeTab === "custom" || activeTab === "builtin";
  const installedSkills = useSkills(agentId, { enabled: onInstalledTab });

  const noAgent = (
    <Empty
      description={t("skills.noAgentSelected")}
      style={{ marginTop: 64 }}
    />
  );

  return (
    <div className={styles.skillsTabs}>
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab}${
            activeTab === "custom" ? ` ${styles.active}` : ""
          }`}
          onClick={() => setActiveTab("custom")}
        >
          {t("skills.customizedSkills")}
        </button>
        <button
          className={`${styles.tab}${
            activeTab === "builtin" ? ` ${styles.active}` : ""
          }`}
          onClick={() => setActiveTab("builtin")}
        >
          {t("skills.builtinSkills")}
        </button>
        <button
          className={`${styles.tab}${
            activeTab === "skillhub" ? ` ${styles.active}` : ""
          }`}
          onClick={() => setActiveTab("skillhub")}
        >
          {t("skills.tencentSkillHub")}
        </button>
      </div>

      <div className={styles.skillsTabsContent}>
        {activeTab === "custom" || activeTab === "builtin" ? (
          agentId ? (
            <InstalledSkillsTab
              key={agentId}
              kind={activeTab === "builtin" ? "builtin" : "custom"}
              {...installedSkills}
            />
          ) : (
            noAgent
          )
        ) : agentId ? (
          <SkillHubTab key={agentId} activeAgentId={agentId} />
        ) : (
          noAgent
        )}
      </div>
    </div>
  );
}
