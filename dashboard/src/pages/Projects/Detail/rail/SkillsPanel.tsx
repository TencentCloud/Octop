import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Empty, Select, Spin, Tag, Tooltip, Typography } from "antd";
import { Plus, X } from "lucide-react";

import {
  projectConfigApi,
  type ProjectSkillWriteItem,
  type ProjectSkillsState,
} from "../../../../api/modules/projectConfig";
import { useProjectMembers } from "../../../../hooks/useProjectMembers";
import { useSkills } from "../../../Agent/Skills/useSkills";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
import SearchablePickerPanel from "../../../../components/ChatPicker/SearchablePickerPanel";
import styles from "./SkillsPanel.module.less";

const { Text } = Typography;

const EMPTY_STATE: ProjectSkillsState = { effective: [], stale: [] };

interface SkillsPanelProps {
  projectId: string;
  /** `PROJECT_MANAGE_CONFIG`（owner/admin）才可增删声明。 */
  canManage: boolean;
}

/**
 * 只列出**该 agent 已安装**的技能（Q9：项目声明是 agent 技能集的投影）。
 * `useSkills` 打的是 agent 侧的既有枚举，因此下拉里不可能出现未安装的技能；
 * 后端仍会再校验一次（409 `PROJECT_SKILL_INVALID`）。
 */
function InstalledSkillSelect({
  agentId,
  value,
  onChange,
}: {
  agentId: string | null;
  value: string | null;
  onChange: (slug: string | null) => void;
}) {
  const { t } = useTranslation();
  const { skills, loading } = useSkills(agentId);
  /* 形态统一到图 2（AC-C-1）：列表交给骨架；★ 功能不变 —— 选中后仍由外层
     「添加」按钮走既有 `write()`（同签名）。 */
  return (
    <div className={styles.addControl} data-testid="picker-panel">
      {loading ? (
        <Spin size="small" />
      ) : (
        <SearchablePickerPanel<{ slug: string; name: string }>
          items={skills.map((skill) => ({
            slug: skill.slug,
            name: skill.name,
          }))}
          filterFn={(skill, query) =>
            `${skill.name}\n${skill.slug}`.toLowerCase().includes(query)
          }
          searchPlaceholder={t("projects.quickInputRecipientFilter")}
          emptyMessage={t("projects.skillNone")}
          renderItem={(skill) => (
            <Button
              key={skill.slug}
              type="text"
              size="small"
              block
              className={styles.addOption}
              data-testid={`picker-option-skill-${skill.slug}`}
              aria-pressed={value === skill.slug}
              onClick={() => onChange(skill.slug)}
            >
              {skill.name}
            </Button>
          )}
          footerIcon={<Plus size={15} aria-hidden />}
          footerLabel={t("projects.skillAdd")}
          onFooterClick={() => undefined}
        />
      )}
    </div>
  );
}
/**
 * 右栏「技能」面板（PLAN §2.3 · Q9）。
 *
 * `effective` = 声明 ∩ 枚举；`stale` = 已声明但当前不可枚举 —— **显式标注失效**
 * 而不是隐藏；写侧不得持久化脱节声明（stale 项只能在 PUT 时被移除或等技能恢复）。
 * `kind` 由后端给出（S3 包优先），这里**只展示不判定**。
 */
export default function SkillsPanel({
  projectId,
  canManage,
}: SkillsPanelProps) {
  const { t } = useTranslation();
  const { members } = useProjectMembers(projectId);
  const [state, setState] = useState<ProjectSkillsState>(EMPTY_STATE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [adding, setAdding] = useState(false);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [slug, setSlug] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setAdding(false);
    setAgentId(null);
    setSlug(null);
    projectConfigApi
      .getSkills(projectId)
      .then((data) => {
        if (!cancelled) setState(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const agentIds = useMemo(
    () =>
      members
        .filter((member) => member.subject_type === "agent")
        .map((member) => member.subject_id),
    [members],
  );

  const write = useCallback(
    async (items: ProjectSkillWriteItem[]) => {
      if (saving) return;
      setSaving(true);
      try {
        setState(await projectConfigApi.putSkills(projectId, items));
        setAdding(false);
        setSlug(null);
      } catch (err) {
        message.error(apiErrorMessage(err, t("projects.skillUnavailable"), t));
      } finally {
        setSaving(false);
      }
    },
    [projectId, saving, t],
  );

  const effectiveItems: ProjectSkillWriteItem[] = state.effective.map(
    (item) => ({
      agent_id: item.agent_id,
      skill_slug: item.skill_slug,
    }),
  );

  const isEmpty = state.effective.length === 0 && state.stale.length === 0;

  return (
    <section className={styles.panel} data-testid="rail-skills">
      <div className={styles.header}>
        <span className={styles.title}>{t("projects.skillTitle")}</span>
        {canManage ? (
          <Button
            type="text"
            size="small"
            aria-label={t("projects.skillAdd")}
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
          description={apiErrorMessage(error, t("projects.skillTitle"), t)}
        />
      ) : isEmpty ? (
        <Text type="secondary" data-testid="skills-empty">
          {t("projects.skillNone")}
        </Text>
      ) : (
        <ul className={styles.list}>
          {state.effective.map((item) => (
            <li
              key={`${item.agent_id}:${item.skill_slug}`}
              className={styles.row}
              data-testid={`skill-${item.skill_slug}`}
            >
              {/* S3：kind 由后端判定（package 优先），前端只展示。 */}
              <Tag className={styles.kindTag}>{item.kind}</Tag>
              <span className={styles.rowName}>{item.display_name}</span>
              <Text type="secondary" className={styles.rowMeta}>
                {item.agent_id}
              </Text>
              {canManage ? (
                <Button
                  type="text"
                  size="small"
                  aria-label={t("common.delete")}
                  icon={<X size={14} />}
                  onClick={() =>
                    void write(
                      effectiveItems.filter(
                        (row) =>
                          !(
                            row.agent_id === item.agent_id &&
                            row.skill_slug === item.skill_slug
                          ),
                      ),
                    )
                  }
                />
              ) : null}
            </li>
          ))}
          {state.stale.map((item) => (
            <li
              key={`stale:${item.agent_id}:${item.skill_slug}`}
              className={`${styles.row} ${styles.staleRow}`}
              data-testid={`skill-stale-${item.skill_slug}`}
            >
              {/* 失效项**显式标注**而不是隐藏。 */}
              <Tooltip title={item.reason}>
                <span className={styles.staleTag}>
                  {t("projects.skillStale")}
                </span>
              </Tooltip>
              <span className={styles.rowName}>{item.skill_slug}</span>
              <Text type="secondary" className={styles.rowMeta}>
                {item.agent_id}
              </Text>
              {canManage ? (
                <Button
                  type="text"
                  size="small"
                  aria-label={t("common.delete")}
                  icon={<X size={14} />}
                  // 显式清理：写侧只提交仍有效的声明。
                  onClick={() => void write(effectiveItems)}
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {canManage && adding ? (
        <div className={styles.addBox}>
          <Text type="secondary" className={styles.addHint}>
            {t("projects.skillUnavailable")}
          </Text>
          <Select
            size="small"
            className={styles.addControl}
            value={agentId ?? undefined}
            aria-label={t("projects.expertTitle")}
            placeholder={t("projects.expertTitle")}
            onChange={(next) => {
              setAgentId(next ?? null);
              setSlug(null);
            }}
            options={agentIds.map((id) => ({ value: id, label: id }))}
          />
          <InstalledSkillSelect
            agentId={agentId}
            value={slug}
            onChange={setSlug}
          />
          <Button
            type="primary"
            size="small"
            loading={saving}
            disabled={!agentId || !slug}
            aria-label={t("projects.skillAdd")}
            onClick={() =>
              void write([
                ...effectiveItems,
                { agent_id: agentId as string, skill_slug: slug as string },
              ])
            }
          />
        </div>
      ) : null}
    </section>
  );
}
