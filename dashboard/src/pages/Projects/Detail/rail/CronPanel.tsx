import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  Checkbox,
  Empty,
  Input,
  Select,
  Spin,
  Tooltip,
  Typography,
} from "antd";
import { Plus, Trash2 } from "lucide-react";

import {
  projectConfigApi,
  type ProjectCronCreateBody,
  type ProjectCronJob,
} from "../../../../api/modules/projectConfig";
import { useProjectMembers } from "../../../../hooks/useProjectMembers";
import { useServerTimezone } from "../../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
import { showConfirmModal } from "../../../../utils/confirmModal";
import { formatServerDateTime } from "../../../../utils/formatMessageTime";
import styles from "./CronPanel.module.less";

const { Text } = Typography;

interface CronPanelProps {
  projectId: string;
  /** `PROJECT_MANAGE_CONFIG` 决定能否进入「新建」；单个 job 仍只限本人改。 */
  canManage: boolean;
}

const EMPTY_DRAFT: ProjectCronCreateBody = {
  name: "",
  agent_id: "",
  schedule_spec: "",
  prompt: "",
  enabled: true,
};

/**
 * 右栏「定时任务」面板（PLAN §3.3 · S4 · FIND-4）。
 *
 * - **可见性 = 本人**（后端只列自己的 job）；**可写性 = 本人**：
 *   `owner`/`admin` 也不能改他人创建的 job → 非 `owned_by_me` 行只读。
 * - **S4**：执行者 agent 未运行 → 仍正常列出，只附灰点标注，**不禁用不隐藏**。
 * - **防御路径**：`prompt_hidden` 行（主行为下不出现）显示「正文已隐藏（其他成员
 *   创建）」并**绝不渲染 prompt**。
 */
export default function CronPanel({ projectId, canManage }: CronPanelProps) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const { members } = useProjectMembers(projectId);
  const [jobs, setJobs] = useState<ProjectCronJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ProjectCronCreateBody>(EMPTY_DRAFT);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setCreating(false);
    setDraft(EMPTY_DRAFT);
    projectConfigApi
      .listCron(projectId)
      .then((rows) => {
        if (!cancelled) setJobs(rows);
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

  const create = useCallback(async () => {
    if (saving) return;
    const name = draft.name.trim();
    const agentId = draft.agent_id.trim();
    const spec = draft.schedule_spec.trim();
    if (!name || !agentId || !spec) return;
    setSaving(true);
    try {
      const created = await projectConfigApi.createCron(projectId, {
        ...draft,
        name,
        agent_id: agentId,
        schedule_spec: spec,
      });
      setJobs((current) => [...current, created]);
      setDraft(EMPTY_DRAFT);
      setCreating(false);
    } catch (err) {
      message.error(apiErrorMessage(err, t("projects.cronCreate"), t));
    } finally {
      setSaving(false);
    }
  }, [draft, projectId, saving, t]);

  const patch = useCallback(
    async (job: ProjectCronJob, body: { enabled?: boolean }) => {
      try {
        const updated = await projectConfigApi.patchCron(
          projectId,
          job.cron_id,
          body,
        );
        setJobs((current) =>
          current.map((row) => (row.cron_id === job.cron_id ? updated : row)),
        );
      } catch (err) {
        message.error(apiErrorMessage(err, t("projects.cronTitle"), t));
      }
    },
    [projectId, t],
  );

  const remove = useCallback(
    (job: ProjectCronJob) => {
      showConfirmModal({
        title: t("projects.cronDeleteConfirm"),
        okText: t("common.delete"),
        cancelText: t("common.cancel"),
        okButtonProps: { danger: true },
        onOk: () => {
          void projectConfigApi
            .deleteCron(projectId, job.cron_id)
            .then(() =>
              setJobs((current) =>
                current.filter((row) => row.cron_id !== job.cron_id),
              ),
            )
            .catch((err: unknown) =>
              message.error(apiErrorMessage(err, t("projects.cronTitle"), t)),
            );
        },
      });
    },
    [projectId, t],
  );

  return (
    <section className={styles.panel} data-testid="rail-cron">
      <div className={styles.header}>
        <span className={styles.title}>{t("projects.cronTitle")}</span>
        {canManage ? (
          <Button
            type="text"
            size="small"
            aria-label={t("projects.cronCreate")}
            icon={<Plus size={14} />}
            onClick={() => setCreating((value) => !value)}
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
          description={apiErrorMessage(error, t("projects.cronTitle"), t)}
        />
      ) : jobs.length === 0 ? (
        <Text type="secondary" data-testid="cron-empty">
          {t("projects.cronNone")}
        </Text>
      ) : (
        <ul className={styles.list}>
          {jobs.map((job) => {
            const writable = canManage && job.owned_by_me;
            return (
              <li
                key={job.cron_id}
                className={styles.row}
                data-testid={`cron-${job.cron_id}`}
              >
                <div className={styles.rowMain}>
                  <span className={styles.rowName}>{job.name}</span>
                  <Text type="secondary" className={styles.rowMeta}>
                    {job.schedule_spec}
                  </Text>
                  <span className={styles.agentLine}>
                    {job.agent_running ? null : (
                      // S4：未运行只做灰点标注 —— 行照常列出、不禁用、不报错。
                      <span
                        className={styles.agentIdleDot}
                        data-testid="cron-agent-idle"
                        title={job.agent_id}
                        aria-hidden
                      />
                    )}
                    <Text type="secondary" className={styles.rowMeta}>
                      {job.agent_id}
                    </Text>
                  </span>
                  {job.prompt_hidden ? (
                    // 防御路径：他人 job 的正文永不下发，也不渲染。
                    <Text type="secondary" data-testid="cron-prompt-hidden">
                      {`${t("projects.cronPromptHidden")} · ${t(
                        "projects.cronOwnedByOther",
                      )}`}
                    </Text>
                  ) : null}
                  {job.last_run_at ? (
                    <Text type="secondary" className={styles.rowMeta}>
                      {formatServerDateTime(job.last_run_at, timeZone)}
                      {job.last_status ? ` · ${job.last_status}` : ""}
                    </Text>
                  ) : null}
                </div>
                <div className={styles.rowActions}>
                  <Tooltip
                    title={
                      job.enabled
                        ? t("projects.cronDisable")
                        : t("projects.cronEnable")
                    }
                  >
                    <Checkbox
                      checked={job.enabled}
                      disabled={!writable}
                      aria-label={
                        job.enabled
                          ? t("projects.cronDisable")
                          : t("projects.cronEnable")
                      }
                      onChange={(event) =>
                        void patch(job, { enabled: event.target.checked })
                      }
                    />
                  </Tooltip>
                  {writable ? (
                    <Button
                      type="text"
                      size="small"
                      aria-label={t("projects.cronDeleteConfirm")}
                      icon={<Trash2 size={14} />}
                      onClick={() => remove(job)}
                    />
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {canManage && creating ? (
        <div className={styles.addBox}>
          <Input
            size="small"
            value={draft.name}
            placeholder={t("projects.cronCreate")}
            aria-label={t("projects.cronCreate")}
            onChange={(event) =>
              setDraft((current) => ({ ...current, name: event.target.value }))
            }
          />
          <Select
            size="small"
            className={styles.addControl}
            value={draft.agent_id || undefined}
            aria-label={t("projects.expertTitle")}
            placeholder={t("projects.expertTitle")}
            onChange={(next) =>
              setDraft((current) => ({ ...current, agent_id: next ?? "" }))
            }
            options={agentIds.map((id) => ({ value: id, label: id }))}
          />
          <Input
            size="small"
            value={draft.schedule_spec}
            placeholder="cron"
            aria-label="cron"
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                schedule_spec: event.target.value,
              }))
            }
          />
          <Input
            size="small"
            value={draft.prompt}
            placeholder={t("projects.cronTitle")}
            aria-label={t("projects.cronTitle")}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                prompt: event.target.value,
              }))
            }
          />
          <Button
            type="primary"
            size="small"
            loading={saving}
            disabled={
              !draft.name.trim() ||
              !draft.agent_id.trim() ||
              !draft.schedule_spec.trim()
            }
            aria-label={t("projects.cronCreate")}
            onClick={() => void create()}
          />
        </div>
      ) : null}
    </section>
  );
}
