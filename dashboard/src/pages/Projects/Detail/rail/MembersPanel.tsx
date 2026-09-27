import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Empty, Input, Select, Spin, Tag, Typography } from "antd";
import { Plus, UserMinus } from "lucide-react";

import {
  projectsApi,
  type ProjectMember,
  type ProjectMemberRole,
  type ProjectSubjectType,
} from "../../../../api/modules/projects";
import { useProjectMembers } from "../../../../hooks/useProjectMembers";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
import styles from "./MembersPanel.module.less";

const { Text } = Typography;

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
  const [subjectType, setSubjectType] = useState<ProjectSubjectType>("user");
  const [subjectId, setSubjectId] = useState("");
  const [role, setRole] = useState<ProjectMemberRole>("member");
  const [saving, setSaving] = useState(false);

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

  const addMember = useCallback(async () => {
    const id = subjectId.trim();
    if (!id || saving) return;
    setSaving(true);
    try {
      await projectsApi.addMember(projectId, {
        subject_type: subjectType,
        subject_id: id,
        role,
      });
      await reload(rows);
      setSubjectId("");
      setAdding(false);
    } catch (err) {
      message.error(apiErrorMessage(err, t("projects.memberAdd"), t));
    } finally {
      setSaving(false);
    }
  }, [projectId, reload, role, rows, saving, subjectId, subjectType, t]);

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
              <Tag className={styles.kindTag}>{member.subject_type}</Tag>
              <span className={styles.rowName}>{member.subject_id}</span>
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
          <Select<ProjectSubjectType>
            size="small"
            value={subjectType}
            aria-label={t("projects.memberTitle")}
            onChange={setSubjectType}
            options={[
              { value: "user", label: "user" },
              { value: "agent", label: "agent" },
              { value: "team", label: "team" },
            ]}
          />
          <Input
            size="small"
            value={subjectId}
            placeholder={t("projects.memberAdd")}
            aria-label={t("projects.memberAdd")}
            onChange={(event) => setSubjectId(event.target.value)}
            onPressEnter={() => void addMember()}
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
          <Button
            type="primary"
            size="small"
            loading={saving}
            disabled={!subjectId.trim()}
            aria-label={t("projects.memberAdd")}
            onClick={() => void addMember()}
          />
        </div>
      ) : null}
    </section>
  );
}
