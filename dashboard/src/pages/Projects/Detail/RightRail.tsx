import { Descriptions, Tag } from "antd";
import { useTranslation } from "react-i18next";

import type { ProjectOut } from "../../../api/modules/projects";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import ConnectorsPanel from "./rail/ConnectorsPanel";
import CronPanel from "./rail/CronPanel";
import ExpertsPanel from "./rail/ExpertsPanel";
import InstructionPanel from "./rail/InstructionPanel";
import MembersPanel from "./rail/MembersPanel";
import SkillsPanel from "./rail/SkillsPanel";
import styles from "./RightRail.module.less";

interface RightRailProps {
  projectId: string;
  /** 概览面板（G2 起迁入右栏第 1 位）所需的项目行与服务器时区。 */
  project: ProjectOut;
  timeZone: string;
  /** 项目状态文案/色（唯一来源 = `Detail/index.tsx` 的 `Record<ProjectStatus, string>`）。 */
  statusLabel: string;
  statusColor: string;
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
  project,
  timeZone,
  statusLabel,
  statusColor,
  canManageConfig,
  canManageMembers,
}: RightRailProps) {
  const { t } = useTranslation();

  return (
    <aside className={styles.rail} data-testid="project-right-rail">
      <div className={styles.railTitle}>{t("projects.configTitle")}</div>
      {/* G2（PLAN §2.3）：概览迁入右栏并**置首** —— 它是「页面级信息」，先于配置类
          面板；数据源不变（仍 `project` 行 + 服务端时区），6 项 / column=2 冻结。 */}
      <section className={styles.overview} data-testid="rail-overview">
        <div
          className={styles.overviewTitle}
          /* projectId 仍挂概览标题的 title 属性（批次三 §2.5 偏差随迁，判定元素不变）。 */
          title={project.project_id}
        >
          {t("projects.overview")}
          <Tag color={statusColor}>{statusLabel}</Tag>
        </div>
        <Descriptions
          column={2}
          size="small"
          colon={false}
          className={styles.overviewMeta}
          data-testid="project-overview"
        >
          <Descriptions.Item label={t("projects.goal")} span={2}>
            {project.goal || t("projects.noGoal")}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.startAt")}>
            {formatServerDateTime(project.start_at ?? 0, timeZone)}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.dueAt")}>
            {formatServerDateTime(project.due_at ?? 0, timeZone)}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.owner")}>
            {project.owner_user_id}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.createdAt")}>
            {formatServerDateTime(project.created_at, timeZone)}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.updatedAt")}>
            {formatServerDateTime(project.updated_at, timeZone)}
          </Descriptions.Item>
        </Descriptions>
      </section>
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
