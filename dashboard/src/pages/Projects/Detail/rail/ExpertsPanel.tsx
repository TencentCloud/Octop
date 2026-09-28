import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Empty, Spin, Tag, Typography } from "antd";
import { Plus, UserMinus } from "lucide-react";

import {
  projectsApi,
  type ProjectMember,
  type ProjectSubjectType,
} from "../../../../api/modules/projects";
import { teamsApi, type TeamRecord } from "../../../../api/modules/teams";
import { useAgent } from "../../../../context/AgentContext";
import { useProjectMembers } from "../../../../hooks/useProjectMembers";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
import {
  KIND_LABEL_KEYS,
  ProjectSubjectPicker,
  type ProjectSubjectKind,
  type ProjectSubjectOption,
} from "./ProjectSubjectPicker";
import styles from "./ExpertsPanel.module.less";

const { Text } = Typography;

interface ExpertsPanelProps {
  projectId: string;
  /** 成员管理走 `PROJECT_MANAGE_MEMBERS`（**不是** `MANAGE_CONFIG`）。 */
  canManageMembers: boolean;
}

/**
 * 右栏「专家」面板（PLAN §7）。
 *
 * **0 张新表**：专家 = `project_members` 里 `subject_type ∈ {agent, team}` 的
 * 行，与「成员」是同一份数据的两种呈现；数据源只有 `GET /projects/{pid}/members`。
 */
export default function ExpertsPanel({
  projectId,
  canManageMembers,
}: ExpertsPanelProps) {
  const { t } = useTranslation();
  const { members, loading, error } = useProjectMembers(projectId);
  /** 增删后本地覆盖，避免为一次写操作把整页重新挂载。 */
  const [override, setOverride] = useState<ProjectMember[] | null>(null);
  const [adding, setAdding] = useState(false);
  /** 候选类别：默认专家；团队与其行语义一致（本面板行含 agent+team）。 */
  const [kind, setKind] = useState<ProjectSubjectKind>("agent");
  const [teams, setTeams] = useState<TeamRecord[] | null>(null);
  const [teamsFailed, setTeamsFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  /** 专家候选 = `GET /api/agents`（`AgentContext` 全局已取，零新增端点）。 */
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
  const experts = rows.filter(
    (member) =>
      member.subject_type === "agent" || member.subject_type === "team",
  );

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

  /** 加入专家：**提交体与改前同签名**（`subject_type`/`subject_id`）。 */
  const addExpert = useCallback(
    async (nextKind: ProjectSubjectKind, subjectId: string) => {
      const id = subjectId.trim();
      if (!id || saving) return;
      setSaving(true);
      try {
        await projectsApi.addMember(projectId, {
          subject_type: nextKind,
          subject_id: id,
        });
        await reload(rows);
        setAdding(false);
      } catch (err) {
        message.error(apiErrorMessage(err, t("projects.expertAdd"), t));
      } finally {
        setSaving(false);
      }
    },
    [projectId, reload, rows, saving, t],
  );

  const pickerLoading =
    kind === "agent" ? agentsLoading : teams === null && !teamsFailed;
  const pickerFailed = kind === "agent" ? agentsError !== null : teamsFailed;

  const removeExpert = useCallback(
    async (type: ProjectSubjectType, id: string) => {
      try {
        await projectsApi.removeMember(projectId, type, id);
        await reload(rows.filter((row) => row.subject_id !== id));
      } catch (err) {
        message.error(apiErrorMessage(err, t("projects.expertAdd"), t));
      }
    },
    [projectId, reload, rows, t],
  );

  return (
    <section className={styles.panel} data-testid="rail-experts">
      <div className={styles.header}>
        <span className={styles.title}>{t("projects.expertTitle")}</span>
        {canManageMembers ? (
          <Button
            type="text"
            size="small"
            aria-label={t("projects.expertAdd")}
            icon={<Plus size={14} />}
            onClick={() => setAdding((value) => !value)}
          />
        ) : null}
      </div>

      {loading ? (
        <div className={styles.centered}>
          <Spin size="small" />
        </div>
      ) : error ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={apiErrorMessage(error, t("projects.expertTitle"), t)}
        />
      ) : experts.length === 0 ? (
        <Text type="secondary" data-testid="experts-empty">
          {t("projects.expertNone")}
        </Text>
      ) : (
        <ul className={styles.list}>
          {experts.map((expert) => (
            <li
              key={`${expert.subject_type}:${expert.subject_id}`}
              className={styles.row}
              data-testid={`expert-${expert.subject_id}`}
            >
              {/* 与 MembersPanel 同一套既有中文键（subjectAgent/subjectTeam）。 */}
              <Tag className={styles.kindTag}>
                {t(KIND_LABEL_KEYS[expert.subject_type as ProjectSubjectKind])}
              </Tag>
              {/* 同一回退规则：有名字显示名字，取不到 → subject_id（不得空白）。 */}
              <span className={styles.rowName}>
                {expert.name?.trim() ? expert.name : expert.subject_id}
              </span>
              {canManageMembers ? (
                <Button
                  type="text"
                  size="small"
                  aria-label={t("common.delete")}
                  icon={<UserMinus size={14} />}
                  onClick={() =>
                    void removeExpert(expert.subject_type, expert.subject_id)
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
              if (option.joined) return;
              void addExpert(option.kind, option.id);
            }}
            emptyMessage={
              kind === "agent"
                ? t("projects.expertNone")
                : t("projects.pickerEmptyTeams")
            }
          />
        </div>
      ) : null}
    </section>
  );
}
