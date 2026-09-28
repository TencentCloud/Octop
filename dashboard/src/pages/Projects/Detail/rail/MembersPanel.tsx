import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Empty, Select, Spin, Tag, Typography } from "antd";
import { Plus, UserMinus } from "lucide-react";

import {
  projectsApi,
  type ProjectMember,
  type ProjectMemberRole,
  type ProjectSubjectType,
} from "../../../../api/modules/projects";
import { teamsApi, type TeamRecord } from "../../../../api/modules/teams";
import { useAgent } from "../../../../context/AgentContext";
import { useProjectMembers } from "../../../../hooks/useProjectMembers";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
import { ProjectSubjectPicker } from "./ProjectSubjectPicker";
import type {
  ProjectSubjectKind,
  ProjectSubjectOption,
} from "./ProjectSubjectPicker";
import styles from "./MembersPanel.module.less";

const { Text } = Typography;

/** 主体类型枚举 → **既有中文键**（批次六 PLAN §2.1；零新增键）。 */
const SUBJECT_LABEL_KEYS: Record<ProjectSubjectType, string> = {
  user: "projects.subjectUser",
  agent: "projects.subjectAgent",
  team: "projects.subjectTeam",
};

const ROLE_LABEL_KEYS: Record<ProjectMemberRole, string> = {
  owner: "projects.memberRoleOwner",
  admin: "projects.memberRoleAdmin",
  member: "projects.memberRoleMember",
  viewer: "projects.memberRoleViewer",
};

interface MembersPanelProps {
  projectId: string;
  /** 成员增删走 `PROJECT_MANAGE_MEMBERS`。 */
  canManageMembers: boolean;
}

/**
 * 右栏「成员」面板（PLAN §7 · R19）。
 *
 * 这是**成员唯一入口**：`Detail/index.tsx` 的旧「成员」section 由 T-FE-DETAIL
 * 移除后，成员管理只在这里；`membersHint` / `membersEmpty` **只允许出现在本组件**。
 * 权限是 `PROJECT_MANAGE_MEMBERS`，不是 `MANAGE_CONFIG`。
 */
export default function MembersPanel({
  projectId,
  canManageMembers,
}: MembersPanelProps) {
  const { t } = useTranslation();
  const { members, loading, error } = useProjectMembers(projectId);
  /** 增删后本地覆盖，避免为一次写操作把整页重新挂载。 */
  const [override, setOverride] = useState<ProjectMember[] | null>(null);
  const [adding, setAdding] = useState(false);
  /** 选择器的候选类别：专家 / 团队（★ **不做「选用户」** — 批次一 `@867` 纪律）。 */
  const [kind, setKind] = useState<ProjectSubjectKind>("agent");
  const [teams, setTeams] = useState<TeamRecord[] | null>(null);
  const [teamsFailed, setTeamsFailed] = useState(false);
  const [role, setRole] = useState<ProjectMemberRole>("member");
  const [saving, setSaving] = useState(false);
  /** 候选数据源（既有端点）：专家 = `GET /api/agents`（`AgentContext` 全局已取）。 */
  const {
    agents,
    loading: agentsLoading,
    error: agentsError,
    refresh,
  } = useAgent();

  useEffect(() => {
    setOverride(null);
    setAdding(false);
  }, [projectId]);

  const rows = override ?? members;

  const reload = useCallback(
    async (fallback: ProjectMember[]) => {
      try {
        setOverride(await projectsApi.listMembers(projectId));
      } catch {
        setOverride(fallback);
      }
    },
    [projectId],
  );

  const loadTeams = useCallback(async () => {
    setTeamsFailed(false);
    try {
      setTeams(await teamsApi.list());
    } catch {
      setTeamsFailed(true);
    }
  }, []);

  // 团队候选按需取（第一次切到「团队」时）；失败 → 可重试（不静默空列表）。
  useEffect(() => {
    if (adding && kind === "team" && teams === null && !teamsFailed) {
      void loadTeams();
    }
  }, [adding, kind, loadTeams, teams, teamsFailed]);

  const options = useMemo<ProjectSubjectOption[]>(() => {
    const joinedIds = new Set(
      rows
        .filter((member) => member.subject_type === kind)
        .map((member) => member.subject_id),
    );
    if (kind === "agent") {
      return agents.map((agent) => ({
        kind: "agent",
        id: agent.agent_id,
        name: agent.name,
        description: agent.description ?? undefined,
        joined: joinedIds.has(agent.agent_id),
      }));
    }
    return (teams ?? []).map((team) => ({
      kind: "team",
      id: team.team_id,
      name: team.name,
      description: team.description ?? undefined,
      joined: joinedIds.has(team.team_id),
    }));
  }, [agents, kind, rows, teams]);

  /** 加入成员：**提交体与改前同签名**（`subject_type`/`subject_id`/`role`）。 */
  const addMember = useCallback(
    async (nextKind: ProjectSubjectKind, subjectId: string) => {
      const id = subjectId.trim();
      if (!id || saving) return;
      setSaving(true);
      try {
        await projectsApi.addMember(projectId, {
          subject_type: nextKind,
          subject_id: id,
          role,
        });
        await reload(rows);
        setAdding(false);
      } catch (err) {
        message.error(apiErrorMessage(err, t("projects.memberAdd"), t));
      } finally {
        setSaving(false);
      }
    },
    [projectId, reload, role, rows, saving, t],
  );

  const pickerLoading =
    kind === "agent" ? agentsLoading : teams === null && !teamsFailed;
  const pickerFailed = kind === "agent" ? agentsError !== null : teamsFailed;

  const removeMember = useCallback(
    async (type: ProjectSubjectType, id: string) => {
      try {
        await projectsApi.removeMember(projectId, type, id);
        await reload(rows.filter((row) => row.subject_id !== id));
      } catch (err) {
        message.error(apiErrorMessage(err, t("projects.memberAdd"), t));
      }
    },
    [projectId, reload, rows, t],
  );

  return (
    <section className={styles.panel} data-testid="rail-members">
      <div className={styles.header}>
        <span className={styles.title}>{t("projects.memberTitle")}</span>
        {canManageMembers ? (
          <Button
            type="text"
            size="small"
            data-testid="member-add-picker"
            aria-label={t("projects.memberAdd")}
            icon={<Plus size={14} />}
            onClick={() => setAdding((value) => !value)}
          />
        ) : null}
      </div>

      {/* S8：旧锚点静默失效后，用一行既有说明把成员管理的归属讲清楚。 */}
      <Text type="secondary" className={styles.hint}>
        {t("projects.membersHint")}
      </Text>

      {loading ? (
        <div className={styles.centered}>
          <Spin size="small" />
        </div>
      ) : error ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={apiErrorMessage(error, t("projects.memberTitle"), t)}
        />
      ) : rows.length === 0 ? (
        <Text type="secondary" data-testid="members-empty">
          {t("projects.membersEmpty")}
        </Text>
      ) : (
        <ul className={styles.list}>
          {rows.map((member) => (
            <li
              key={`${member.subject_type}:${member.subject_id}`}
              className={styles.row}
              data-testid={`member-${member.subject_id}`}
            >
              <Tag className={styles.kindTag}>
                {t(SUBJECT_LABEL_KEYS[member.subject_type])}
              </Tag>
              {/* AC-B-2/AC-B-3：有名字显示名字，取不到 → 回退 subject_id（不得空白）。 */}
              <span className={styles.rowName}>
                {member.name?.trim() ? member.name : member.subject_id}
              </span>
              <Text type="secondary" className={styles.rowRole}>
                {t(ROLE_LABEL_KEYS[member.role])}
              </Text>
              {canManageMembers ? (
                <Button
                  type="text"
                  size="small"
                  aria-label={t("common.delete")}
                  icon={<UserMinus size={14} />}
                  onClick={() =>
                    void removeMember(member.subject_type, member.subject_id)
                  }
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {canManageMembers && adding ? (
        <div className={styles.addBox}>
          <ProjectSubjectPicker
            kind={kind}
            onKindChange={setKind}
            options={options}
            loading={pickerLoading}
            failed={pickerFailed}
            onRetry={() => {
              if (kind === "agent") {
                void refresh({ force: true });
                return;
              }
              setTeams(null);
              void loadTeams();
            }}
            onPick={(option) => {
              // R13 / C12：已加入的项不可重复提交。
              if (option.joined) return;
              void addMember(option.kind, option.id);
            }}
            emptyMessage={
              kind === "agent"
                ? t("projects.expertNone")
                : t("projects.pickerEmptyTeams")
            }
          />
          <Select<ProjectMemberRole>
            size="small"
            value={role}
            aria-label={t("projects.memberTitle")}
            onChange={setRole}
            options={(["owner", "admin", "member", "viewer"] as const).map(
              (value) => ({ value, label: t(ROLE_LABEL_KEYS[value]) }),
            )}
          />
        </div>
      ) : null}
    </section>
  );
}
