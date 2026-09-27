import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Checkbox,
  DatePicker,
  Input,
  InputNumber,
  Modal,
  Select,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  Check,
  Flag,
  MoreHorizontal,
  Paperclip,
  Tag as TagIcon,
  Trash2,
  User,
  Users,
  X,
} from "lucide-react";
import dayjs, { type Dayjs } from "dayjs";
import { useTranslation } from "react-i18next";

import {
  projectsApi,
  type ProjectAttachment,
  type ProjectCustomFieldDefinition,
  type ProjectCustomFieldWriteValue,
  type ProjectMember,
  type ProjectTagDefinition,
  type ProjectTask,
  type ProjectTaskStatus,
} from "../../../api/modules/projects";
import { projectMetadataApi } from "../../../api/modules/projectMetadata";
import { useProjectMembers } from "../../../hooks/useProjectMembers";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "../../../utils/antdMessage";
import { ChipButton, ChipToolbar } from "../../../components/ChipToolbar";
import styles from "./TaskCreateModal.module.less";

const { Text } = Typography;

/** PLAN §7.2: single-file ceiling; the server is still authoritative. */
const MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024;

/** Column order for the status picker (PLAN §1.1: planning first). */
const TASK_STATUS_ORDER: ProjectTaskStatus[] = [
  "planning",
  "todo",
  "doing",
  "review",
  "blocked",
  "done",
  "cancelled",
];

const STATUS_LABEL_KEYS: Record<ProjectTaskStatus, string> = {
  planning: "projects.taskStatusPlanning",
  todo: "projects.taskStatusTodo",
  doing: "projects.taskStatusDoing",
  review: "projects.taskStatusReview",
  blocked: "projects.taskStatusBlocked",
  done: "projects.taskStatusDone",
  cancelled: "projects.taskStatusCancelled",
};

const PRIORITY_OPTIONS = [0, 1, 2, 3, 4];

interface Assignee {
  type: string;
  id: string;
}

interface TaskCreateModalProps {
  open: boolean;
  projectId: string;
  /** Existing tasks of this project — the only parent-task source (R5). */
  tasks: ProjectTask[];
  canEdit: boolean;
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}

function toEpochSeconds(value: Dayjs | null): number | null {
  return value ? Math.floor(value.valueOf() / 1000) : null;
}

const memberLabel = (member: ProjectMember) =>
  `${member.subject_type}:${member.subject_id}`;

/**
 * Create-task dialog (R3, SPEC AC-U-8): breadcrumb + inline title + inline
 * description + chip toolbar (status / priority / assignee / tags / project /
 * more) + attachments + "switch to agent" + "keep creating" + ⌘↵ submit.
 *
 * Keyboard (PLAN §10.1): ⌘/Ctrl+Enter submits from anywhere in the dialog,
 * a bare Enter in the title submits, Enter in the description inserts a
 * newline, Esc closes and discards. Every submit path short-circuits while an
 * IME composition is active (S-5) — Enter there picks a candidate, it must
 * never create a task.
 */
export default function TaskCreateModal({
  open,
  projectId,
  tasks,
  canEdit,
  onClose,
  onCreated,
}: TaskCreateModalProps) {
  const { t } = useTranslation();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<ProjectTaskStatus>("planning");
  const [priority, setPriority] = useState(0);
  const [assignee, setAssignee] = useState<Assignee | null>(null);
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [startAt, setStartAt] = useState<Dayjs | null>(null);
  const [dueAt, setDueAt] = useState<Dayjs | null>(null);
  const [parentId, setParentId] = useState<string | null>(null);
  const [customValues, setCustomValues] = useState<
    Record<string, ProjectCustomFieldWriteValue>
  >({});
  const [staged, setStaged] = useState<ProjectAttachment[]>([]);
  const [keepCreating, setKeepCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [projectName, setProjectName] = useState("");
  const [tags, setTags] = useState<ProjectTagDefinition[]>([]);
  const [definitions, setDefinitions] = useState<
    ProjectCustomFieldDefinition[]
  >([]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  // Members only while the dialog is open: the hook is the single member feed
  // (R5 / AC-U-24) and must never touch the global user directory.
  const { members, loading: membersLoading } = useProjectMembers(
    open ? projectId : null,
  );

  // Tag + custom-field definitions are read once per open.
  useEffect(() => {
    if (!open || !projectId) return;
    let cancelled = false;
    projectsApi
      .get(projectId)
      .then((project) => {
        if (!cancelled) setProjectName(project.name);
      })
      .catch(() => undefined);
    projectMetadataApi
      .listTags(projectId)
      .then((rows) => {
        if (!cancelled) setTags(rows);
      })
      .catch(() => undefined);
    projectMetadataApi
      .listCustomFields(projectId)
      .then((rows) => {
        if (!cancelled) setDefinitions(rows);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open, projectId]);

  const agentMembers = useMemo(
    () =>
      members.filter(
        (member) =>
          member.subject_type === "agent" || member.subject_type === "team",
      ),
    [members],
  );

  /** Drop staged (never bound) attachments — best effort, never blocks close. */
  const discardStaged = useCallback(
    (items: ProjectAttachment[]) => {
      for (const item of items) {
        void projectMetadataApi
          .deleteAttachment(projectId, item.artifact_id)
          .catch(() => undefined);
      }
    },
    [projectId],
  );

  const resetForm = useCallback(() => {
    setTitle("");
    setDescription("");
    setStatus("planning");
    setPriority(0);
    setAssignee(null);
    setTagIds([]);
    setStartAt(null);
    setDueAt(null);
    setParentId(null);
    setCustomValues({});
    setStaged([]);
    setKeepCreating(false);
  }, []);

  const handleCancel = () => {
    // PLAN §7.5.6: give up the staged files explicitly; uploads that were
    // already used by a create are bound and must not be touched.
    discardStaged(staged);
    resetForm();
    onClose();
  };

  const submit = async () => {
    if (!canEdit || submitting) return;
    const trimmed = title.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await projectsApi.createTask(projectId, {
        title: trimmed,
        description: description.trim() || undefined,
        status,
        priority,
        assignee_type: assignee?.type ?? null,
        assignee_id: assignee?.id ?? null,
        due_at: toEpochSeconds(dueAt),
        start_at: toEpochSeconds(startAt),
        parent_id: parentId,
        tags: tagIds,
        custom_fields: customValues,
        attachment_ids: staged.map((item) => item.artifact_id),
      });
      message.success(t("projects.boardCreated"));
      await onCreated();
      if (keepCreating) {
        // PLAN §10.2 / S-4: clear title + description + due_at, keep the other
        // eight selections; attachments are already bound, so the list clears.
        setTitle("");
        setDescription("");
        setDueAt(null);
        setStaged([]);
      } else {
        resetForm();
        onClose();
      }
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.boardCreateFailed"), t));
    } finally {
      setSubmitting(false);
    }
  };

  /** S-5: an IME composition owns Enter — never submit, never preventDefault. */
  const composing = (event: React.KeyboardEvent) =>
    event.nativeEvent.isComposing === true;

  const handleContainerKeyDown = (
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if (event.key !== "Enter") return;
    if (!(event.metaKey || event.ctrlKey)) return;
    if (composing(event)) return;
    event.preventDefault();
    void submit();
  };

  const handleTitleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    // ⌘/Ctrl+Enter belongs to the container handler — avoid a double submit.
    if (event.metaKey || event.ctrlKey) return;
    if (composing(event)) return;
    event.preventDefault();
    void submit();
  };

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !projectId) return;
    if (file.size > MAX_ATTACHMENT_BYTES) {
      message.error(t("projects.attachmentTooLarge"));
      return;
    }
    setUploading(true);
    try {
      const uploaded = await projectMetadataApi.uploadPendingAttachment(
        projectId,
        file,
      );
      setStaged((current) => [...current, uploaded]);
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.attachmentBadType"), t));
    } finally {
      setUploading(false);
    }
  };

  const removeStaged = (artifact: ProjectAttachment) => {
    setStaged((current) =>
      current.filter((item) => item.artifact_id !== artifact.artifact_id),
    );
    void projectMetadataApi
      .deleteAttachment(projectId, artifact.artifact_id)
      .catch(() => undefined);
  };

  const moreCount =
    (dueAt ? 1 : 0) +
    (startAt ? 1 : 0) +
    (parentId ? 1 : 0) +
    definitions.filter((definition) => {
      const value = customValues[definition.field_id];
      return value !== undefined && value !== null && value !== "";
    }).length;
  const statusSummary = t(STATUS_LABEL_KEYS[status]);
  const assigneeSummary = assignee ? `${assignee.type}:${assignee.id}` : null;
  const tagSummary =
    tagIds.length > 0
      ? tags
          .filter((tag) => tagIds.includes(tag.tag_id))
          .map((tag) => tag.name)
          .join("、")
      : null;

  const renderStatusPicker = () => (
    <div className={styles.optionList}>
      {TASK_STATUS_ORDER.map((option) => (
        <button
          key={option}
          type="button"
          className={`${styles.option} ${
            option === status ? styles.optionActive : ""
          }`}
          onClick={() => setStatus(option)}
        >
          <span>{t(STATUS_LABEL_KEYS[option])}</span>
          {option === status ? <Check size={14} /> : null}
        </button>
      ))}
    </div>
  );

  const renderPriorityPicker = () => (
    <div className={styles.optionList}>
      {PRIORITY_OPTIONS.map((option) => (
        <button
          key={option}
          type="button"
          className={`${styles.option} ${
            option === priority ? styles.optionActive : ""
          }`}
          onClick={() => setPriority(option)}
        >
          <span>{option}</span>
          {option === priority ? <Check size={14} /> : null}
        </button>
      ))}
    </div>
  );

  const renderAssigneePicker = () => {
    if (membersLoading) {
      return (
        <div className={styles.pickerCentered}>
          <Spin size="small" />
        </div>
      );
    }
    if (members.length === 0) {
      return (
        <div className={styles.pickerEmpty}>{t("projects.noMembers")}</div>
      );
    }
    return (
      <div className={styles.optionList}>
        {members.map((member) => {
          const value = memberLabel(member);
          const active =
            assignee?.type === member.subject_type &&
            assignee?.id === member.subject_id;
          return (
            <button
              key={value}
              type="button"
              className={`${styles.option} ${
                active ? styles.optionActive : ""
              }`}
              onClick={() =>
                setAssignee(
                  active
                    ? null
                    : { type: member.subject_type, id: member.subject_id },
                )
              }
            >
              <span>{value}</span>
              {active ? <Check size={14} /> : null}
            </button>
          );
        })}
      </div>
    );
  };

  const renderTagPicker = () => {
    if (tags.length === 0) {
      return <div className={styles.pickerEmpty}>{t("projects.noTags")}</div>;
    }
    return (
      <div className={styles.optionList}>
        {tags.map((tag) => {
          const active = tagIds.includes(tag.tag_id);
          return (
            <button
              key={tag.tag_id}
              type="button"
              className={`${styles.option} ${
                active ? styles.optionActive : ""
              }`}
              onClick={() =>
                setTagIds((current) =>
                  active
                    ? current.filter((id) => id !== tag.tag_id)
                    : [...current, tag.tag_id],
                )
              }
            >
              <Tag color={tag.color || undefined}>{tag.name}</Tag>
              {active ? <Check size={14} /> : null}
            </button>
          );
        })}
      </div>
    );
  };

  const renderCustomFieldInput = (definition: ProjectCustomFieldDefinition) => {
    const value = customValues[definition.field_id];
    const setValue = (next: ProjectCustomFieldWriteValue) =>
      setCustomValues((current) => ({
        ...current,
        [definition.field_id]: next,
      }));

    if (definition.type === "number") {
      return (
        <InputNumber
          className={styles.fieldControl}
          value={typeof value === "number" ? value : null}
          onChange={(next) => setValue(next ?? null)}
          aria-label={definition.label}
        />
      );
    }
    if (definition.type === "date") {
      const seconds = typeof value === "number" ? value : null;
      return (
        <DatePicker
          className={styles.fieldControl}
          showTime={{ format: "HH:mm" }}
          format="YYYY-MM-DD HH:mm"
          value={seconds ? dayjs(seconds * 1000) : null}
          onChange={(next) => setValue(next ? toEpochSeconds(next) : null)}
          aria-label={definition.label}
        />
      );
    }
    if (definition.type === "select") {
      return (
        <Select
          className={styles.fieldControl}
          allowClear
          value={typeof value === "string" && value ? value : undefined}
          placeholder={definition.label}
          aria-label={definition.label}
          onChange={(next) => setValue(next ?? null)}
          options={definition.options.map((option) => ({
            value: option,
            label: option,
          }))}
        />
      );
    }
    return (
      <Input
        className={styles.fieldControl}
        value={typeof value === "string" ? value : ""}
        placeholder={definition.label}
        aria-label={definition.label}
        onChange={(event) => setValue(event.target.value)}
      />
    );
  };

  const renderMorePanel = () => (
    <div className={styles.morePanel}>
      <div className={styles.moreRow}>
        <span className={styles.moreLabel}>{t("projects.chipDueAt")}</span>
        <DatePicker
          className={styles.fieldControl}
          showTime={{ format: "HH:mm" }}
          format="YYYY-MM-DD HH:mm"
          value={dueAt}
          onChange={(next) => setDueAt(next)}
          aria-label={t("projects.chipDueAt")}
        />
      </div>
      <div className={styles.moreRow}>
        <span className={styles.moreLabel}>{t("projects.chipStartAt")}</span>
        <DatePicker
          className={styles.fieldControl}
          showTime={{ format: "HH:mm" }}
          format="YYYY-MM-DD HH:mm"
          value={startAt}
          onChange={(next) => setStartAt(next)}
          aria-label={t("projects.chipStartAt")}
        />
      </div>
      <div className={styles.moreRow}>
        <span className={styles.moreLabel}>{t("projects.chipParentTask")}</span>
        <Select
          className={styles.fieldControl}
          allowClear
          value={parentId ?? undefined}
          placeholder={
            tasks.length === 0
              ? t("projects.noTasks")
              : t("projects.chipParentTask")
          }
          aria-label={t("projects.chipParentTask")}
          onChange={(next) => setParentId(next ?? null)}
          options={tasks.map((task) => ({
            value: task.task_id,
            label: task.title,
          }))}
        />
      </div>
      <div className={styles.moreRow}>
        <span className={styles.moreLabel}>{t("projects.chipSubtasks")}</span>
        {/* Reverse relation: other tasks point at this one, so nothing can be
            attached before the task exists (SPEC §边界 Case 父/子任务). */}
        <Text type="secondary" className={styles.moreHint}>
          {t("projects.noTasks")}
        </Text>
      </div>
      {definitions.length > 0 ? (
        <>
          <div className={styles.moreDivider} />
          <div className={styles.moreLabel}>
            {t("projects.chipCustomFields")}
          </div>
          {definitions.map((definition) => (
            <div key={definition.field_id} className={styles.moreRow}>
              <span className={styles.moreLabel}>
                {definition.label}
                {definition.required ? (
                  <span className={styles.requiredMark}>*</span>
                ) : null}
              </span>
              {renderCustomFieldInput(definition)}
            </div>
          ))}
        </>
      ) : null}
    </div>
  );

  const renderAgentPicker = () => {
    if (agentMembers.length === 0) {
      return (
        <div className={styles.pickerEmpty}>{t("projects.noMembers")}</div>
      );
    }
    return (
      <div className={styles.optionList}>
        {agentMembers.map((member) => (
          <button
            key={memberLabel(member)}
            type="button"
            className={styles.option}
            onClick={() => {
              // PLAN §8.1: the dialog only writes `assignee` — dispatch stays an
              // explicit task-card action, because the task does not exist yet.
              setAssignee({
                type: member.subject_type,
                id: member.subject_id,
              });
            }}
          >
            {member.subject_type === "team" ? (
              <Users size={14} />
            ) : (
              <User size={14} />
            )}
            <span>{memberLabel(member)}</span>
          </button>
        ))}
      </div>
    );
  };

  return (
    <Modal
      open={open}
      onCancel={handleCancel}
      footer={null}
      width={760}
      destroyOnHidden
      className={styles.modal}
      title={
        <div className={styles.breadcrumb}>
          {projectName ? (
            <>
              <span className={styles.breadcrumbParent}>{projectName}</span>
              <span className={styles.breadcrumbSep} aria-hidden>
                ›
              </span>
            </>
          ) : null}
          <span className={styles.breadcrumbCurrent}>
            {t("projects.createTaskBreadcrumb")}
          </span>
        </div>
      }
    >
      <div className={styles.shell} onKeyDown={handleContainerKeyDown}>
        <input
          className={styles.titleInput}
          value={title}
          maxLength={120}
          autoFocus
          placeholder={t("projects.createTaskTitle")}
          aria-label={t("projects.createTaskTitle")}
          onChange={(event) => setTitle(event.target.value)}
          onKeyDown={handleTitleKeyDown}
        />

        <Input.TextArea
          className={styles.description}
          value={description}
          placeholder={t("projects.createTaskDescription")}
          aria-label={t("projects.createTaskDescription")}
          autoSize={{ minRows: 3, maxRows: 8 }}
          onChange={(event) => setDescription(event.target.value)}
        />

        <ChipToolbar>
          <ChipButton
            icon={<Flag size={14} />}
            label={t("projects.chipStatus")}
            value={statusSummary}
            active
            ariaLabel={t("projects.chipStatus")}
          >
            {renderStatusPicker()}
          </ChipButton>
          <ChipButton
            icon={<Flag size={14} />}
            label={t("projects.chipPriority")}
            value={String(priority)}
            ariaLabel={t("projects.chipPriority")}
          >
            {renderPriorityPicker()}
          </ChipButton>
          <ChipButton
            icon={<User size={14} />}
            label={t("projects.chipAssignee")}
            value={assigneeSummary}
            ariaLabel={t("projects.chipAssignee")}
          >
            {renderAssigneePicker()}
          </ChipButton>
          <ChipButton
            icon={<TagIcon size={14} />}
            label={t("projects.chipTags")}
            value={tagSummary}
            ariaLabel={t("projects.chipTags")}
          >
            {renderTagPicker()}
          </ChipButton>
          <ChipButton
            icon={<Users size={14} />}
            label={t("projects.chipProject")}
            value={projectName || null}
            ariaLabel={t("projects.chipProject")}
          />
          <ChipButton
            icon={<MoreHorizontal size={14} />}
            label={t("projects.chipMore")}
            value={moreCount > 0 ? String(moreCount) : null}
            ariaLabel={t("projects.chipMore")}
          >
            {renderMorePanel()}
          </ChipButton>
        </ChipToolbar>

        {staged.length > 0 ? (
          <div className={styles.attachments}>
            {staged.map((item) => (
              <span key={item.artifact_id} className={styles.attachment}>
                <Paperclip size={12} />
                <span className={styles.attachmentName}>{item.name}</span>
                <button
                  type="button"
                  className={styles.attachmentRemove}
                  aria-label={t("projects.attachmentDeleteConfirm")}
                  onClick={() => removeStaged(item)}
                >
                  <Trash2 size={12} />
                </button>
              </span>
            ))}
          </div>
        ) : (
          <div className={styles.attachmentsEmpty}>
            {t("projects.attachmentsEmpty")}
          </div>
        )}

        <div className={styles.footer}>
          <div className={styles.footerLeft}>
            <input
              ref={fileInputRef}
              type="file"
              className={styles.fileInput}
              onChange={(event) => void handleFileChange(event)}
            />
            <Tooltip title={t("projects.attachFile")}>
              <Button
                type="text"
                aria-label={t("projects.attachFile")}
                loading={uploading}
                icon={<Paperclip size={16} />}
                onClick={() => fileInputRef.current?.click()}
              />
            </Tooltip>
            <span className={styles.footerButton}>
              <ChipButton
                icon={<User size={14} />}
                label={t("projects.switchToAgent")}
                value={
                  assignee &&
                  (assignee.type === "agent" || assignee.type === "team")
                    ? `${assignee.type}:${assignee.id}`
                    : null
                }
                disabled={agentMembers.length === 0}
                ariaLabel={t("projects.switchToAgent")}
              >
                {renderAgentPicker()}
              </ChipButton>
            </span>
            <Checkbox
              className={styles.keepCreating}
              checked={keepCreating}
              onChange={(event) => setKeepCreating(event.target.checked)}
            >
              {t("projects.createAndContinue")}
            </Checkbox>
          </div>
          <div className={styles.footerRight}>
            <Tooltip title={t("common.cancel")}>
              <Button
                type="text"
                aria-label={t("common.cancel")}
                icon={<X size={16} />}
                onClick={handleCancel}
              />
            </Tooltip>
            <Button
              type="primary"
              loading={submitting}
              disabled={!canEdit || !title.trim()}
              onClick={() => void submit()}
            >
              <span className={styles.submitLabel}>
                {t("projects.createTaskSubmit")}
                <span className={styles.shortcutHint}>⌘↵</span>
              </span>
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
