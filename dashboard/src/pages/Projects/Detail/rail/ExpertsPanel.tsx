import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Empty, Input, Select, Spin, Tag, Typography } from "antd";
import { Plus, UserMinus } from "lucide-react";

import {
  projectsApi,
  type ProjectMember,
  type ProjectSubjectType,
} from "../../../../api/modules/projects";
import { useProjectMembers } from "../../../../hooks/useProjectMembers";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
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
  const [subjectType, setSubjectType] = useState<ProjectSubjectType>("agent");
  const [subjectId, setSubjectId] = useState("");
  const [saving, setSaving] = useState(false);

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

  const addExpert = useCallback(async () => {
    const id = subjectId.trim();
    if (!id || saving) return;
    setSaving(true);
    try {
      await projectsApi.addMember(projectId, {
        subject_type: subjectType,
        subject_id: id,
      });
      await reload(rows);
      setSubjectId("");
      setAdding(false);
    } catch (err) {
      message.error(apiErrorMessage(err, t("projects.expertAdd"), t));
    } finally {
      setSaving(false);
    }
  }, [projectId, reload, rows, saving, subjectId, subjectType, t]);

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
              <Tag className={styles.kindTag}>{expert.subject_type}</Tag>
              <span className={styles.rowName}>{expert.subject_id}</span>
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
          <Select<ProjectSubjectType>
            size="small"
            value={subjectType}
            aria-label={t("projects.expertTitle")}
            onChange={setSubjectType}
            options={[
              { value: "agent", label: "agent" },
              { value: "team", label: "team" },
            ]}
          />
          <Input
            size="small"
            value={subjectId}
            placeholder={t("projects.expertAdd")}
            aria-label={t("projects.expertAdd")}
            onChange={(event) => setSubjectId(event.target.value)}
            onPressEnter={() => void addExpert()}
          />
          <Button
            type="primary"
            size="small"
            loading={saving}
            disabled={!subjectId.trim()}
            aria-label={t("projects.expertAdd")}
            onClick={() => void addExpert()}
          />
        </div>
      ) : null}
    </section>
  );
}
