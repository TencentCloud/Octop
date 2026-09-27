import { useTranslation } from "react-i18next";

import ConnectorsPanel from "./rail/ConnectorsPanel";
import CronPanel from "./rail/CronPanel";
import ExpertsPanel from "./rail/ExpertsPanel";
import InstructionPanel from "./rail/InstructionPanel";
import MembersPanel from "./rail/MembersPanel";
import SkillsPanel from "./rail/SkillsPanel";
import styles from "./RightRail.module.less";

interface RightRailProps {
  projectId: string;
  /** `PROJECT_MANAGE_CONFIG`（owner/admin）：决定 4 个配置面板的可见性与可写性。 */
  canManageConfig: boolean;
  /** `PROJECT_MANAGE_MEMBERS`（owner/admin）：成员与专家的增删。 */
  canManageMembers: boolean;
}

/**
 * 右栏容器（PLAN §4 / §6 / §7）。
 *
 * - **常驻**：即使数据为空也保留整个栏（各面板自己渲染空态），不整栏隐藏。
 * - **配置面板按 `MANAGE_CONFIG` 可见**（member/viewer 看不到指令/连接器/技能/
 *   cron 面板及其数据，PLAN §6）；成员与专家面板对所有成员可见，只有写操作
 *   受 `MANAGE_MEMBERS` 限制。
 * - 成员管理是**唯一入口**（R19）：旧 `Detail/index.tsx` 的成员 section 已删除。
 */
export default function RightRail({
  projectId,
  canManageConfig,
  canManageMembers,
}: RightRailProps) {
  const { t } = useTranslation();

  return (
    <aside className={styles.rail} data-testid="project-right-rail">
      <div className={styles.railTitle}>{t("projects.configTitle")}</div>
      {canManageConfig ? (
        <>
          <InstructionPanel projectId={projectId} canManage />
          <ConnectorsPanel projectId={projectId} canManage />
        </>
      ) : null}
      <ExpertsPanel projectId={projectId} canManageMembers={canManageMembers} />
      {canManageConfig ? (
        <>
          <SkillsPanel projectId={projectId} canManage />
          <CronPanel projectId={projectId} canManage />
        </>
      ) : null}
      <MembersPanel projectId={projectId} canManageMembers={canManageMembers} />
    </aside>
  );
}
