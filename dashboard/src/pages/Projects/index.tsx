import { useEffect, useState } from "react";
import {
  Button,
  DatePicker,
  Form,
  Input,
  List,
  Modal,
  Spin,
  Tag,
  Tooltip,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import {
  BookOpen,
  CalendarClock,
  CalendarDays,
  CircleDot,
  FolderKanban,
  Pencil,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type { OctopUser } from "../../api/modules/auth";
import {
  knowledgeBasesApi,
  type KnowledgeBase,
} from "../../api/modules/knowledgeBases";
import {
  projectsApi,
  type ProjectCreateBody,
  type ProjectMember,
  type ProjectMemberRole,
  type ProjectOut,
  type ProjectStatus,
  type ProjectUpdateBody,
} from "../../api/modules/projects";
import { ChipButton, ChipToolbar } from "../../components/ChipToolbar";
import { EmptyState } from "../../components/EmptyState";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useCurrentUser } from "../../hooks/useCurrentUser";
import { useServerTimezone } from "../../hooks/useServerTimezone";
import PageShell from "../../layouts/PageShell";
import { apiErrorMessage } from "../../utils/apiError";
import { message } from "../../utils/antdMessage";
import { formatServerDateTime } from "../../utils/formatMessageTime";
import styles from "./index.module.less";

/**
 * Project status copy (PLAN §3.2 / §3.1): six values, and ``archived`` is a
 * different thing from ``cancelled`` — never share a key between the two.
 */
const STATUS_LABEL_KEYS: Record<ProjectStatus, string> = {
  draft: "projects.statusDraft",
  active: "projects.statusActive",
  paused: "projects.statusPaused",
  completed: "projects.statusCompleted",
  cancelled: "projects.statusCancelled",
  archived: "projects.statusArchived",
};

const STATUS_COLORS: Record<ProjectStatus, string> = {
  draft: "default",
  active: "success",
  paused: "warning",
  completed: "blue",
  cancelled: "error",
  archived: "default",
};

const STATUS_OPTIONS = Object.keys(STATUS_LABEL_KEYS) as ProjectStatus[];

/** Backend default for a fresh project (`repos/projects.py`). */
const DEFAULT_STATUS: ProjectStatus = "draft";

const DATE_FORMAT = "YYYY-MM-DD HH:mm";

function emptyValues(): ProjectFormValues {
  return {
    name: "",
    goal: "",
    status: DEFAULT_STATUS,
    start_at: null,
    due_at: null,
    kb_id: "",
  };
}

interface ProjectFormValues {
  name: string;
  goal?: string;
  status: ProjectStatus;
  start_at?: Dayjs | null;
  due_at?: Dayjs | null;
  /** `""` = not bound; a KB id = bound. Edit mode only (PLAN §4.4). */
  kb_id?: string;
}

/** Current values of the project being edited, as form values (PLAN §3). */
function valuesOf(project: ProjectOut): ProjectFormValues {
  return {
    name: project.name,
    goal: project.goal,
    status: project.status,
    start_at: project.start_at ? dayjs(project.start_at * 1000) : null,
    due_at: project.due_at ? dayjs(project.due_at * 1000) : null,
    kb_id: project.kb_id ?? "",
  };
}

/**
 * Rebindable knowledge bases — mirrors the server's write rule
 * (`KnowledgeService.get_writable_base`: owner **or** platform admin) instead of
 * offering bases the caller would get a 403 for (PLAN §4.4 / acceptance ③).
 */
function writableBases(
  rows: KnowledgeBase[],
  user: OctopUser | null,
): KnowledgeBase[] {
  if (!user) return [];
  return rows.filter(
    (base) => user.role === "admin" || base.owner_user_id === user.id,
  );
}

/** The caller's role in one project, from its member list. */
function roleOf(
  members: ProjectMember[],
  userId: number | undefined,
): ProjectMemberRole | null {
  if (userId === undefined) return null;
  const mine = members.find(
    (member) => member.subject_type === "user" && member.user_id === userId,
  );
  return mine?.role ?? null;
}

function ProjectsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const timeZone = useServerTimezone();
  const currentUser = useCurrentUser();
  const [form] = Form.useForm<ProjectFormValues>();
  const [createOpen, setCreateOpen] = useState(false);
  // ``null`` = create mode; a project = edit mode (same dialog, PLAN §3).
  const [editing, setEditing] = useState<ProjectOut | null>(null);
  const [saving, setSaving] = useState(false);
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [myRole, setMyRole] = useState<ProjectMemberRole | null>(null);
  const status = Form.useWatch("status", form) ?? DEFAULT_STATUS;
  const startAt = Form.useWatch("start_at", form);
  const dueAt = Form.useWatch("due_at", form);
  const kbId = Form.useWatch("kb_id", form) ?? "";

  const {
    data: projects,
    loading,
    refresh,
  } = useAsyncResource<ProjectOut[]>([], () => projectsApi.list(), [], {
    t,
    errorFallback: t("projects.loadFailed"),
    logLabel: "projects",
  });

  const archived = editing?.status === "archived";
  /** `kb_id` needs the config level; without it the field is read-only (PLAN §4.3). */
  const canManageConfig =
    !archived && (myRole === "owner" || myRole === "admin");

  // Editing reads two things the list page does not carry: the caller's role in
  // this project (for the kb permission) and the bases they may write.
  useEffect(() => {
    if (!createOpen || !editing || !currentUser) return;
    let cancelled = false;
    projectsApi
      .listMembers(editing.project_id)
      .then((rows) => {
        if (!cancelled) setMyRole(roleOf(rows, currentUser.id));
      })
      .catch(() => undefined);
    knowledgeBasesApi
      .list()
      .then((rows) => {
        if (!cancelled) setBases(writableBases(rows, currentUser));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [createOpen, editing, currentUser]);

  /**
   * Seed the form store before the modal mounts. ``initialValues`` cannot do
   * this: rc-field-form merges them *under* whatever the store already holds,
   * so a reopened dialog would keep the previous entry.
   */
  const openCreate = () => {
    setEditing(null);
    setMyRole(null);
    setBases([]);
    form.setFieldsValue(emptyValues());
    setCreateOpen(true);
  };

  const openEdit = (project: ProjectOut) => {
    setEditing(project);
    setMyRole(null);
    setBases([]);
    form.setFieldsValue(valuesOf(project));
    setCreateOpen(true);
  };

  const closeCreate = () => {
    setCreateOpen(false);
    setEditing(null);
  };

  const submitForm = async (values: ProjectFormValues) => {
    // Same boundary the server enforces for tasks (PLAN §3): block it up front.
    const startSeconds = values.start_at ? values.start_at.unix() : null;
    const dueSeconds = values.due_at ? values.due_at.unix() : null;
    if (
      startSeconds !== null &&
      dueSeconds !== null &&
      dueSeconds < startSeconds
    ) {
      message.error(t("apiErrors.PROJECT_TASK_DATE_INVALID"));
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        const body: ProjectUpdateBody = {
          name: values.name.trim(),
          // Cleared goal = ``""``, never null (PLAN §3).
          goal: values.goal?.trim() ?? "",
          start_at: startSeconds,
          due_at: dueSeconds,
          clear_start_at: startSeconds === null,
          clear_due_at: dueSeconds === null,
        };
        // Re-sending the current status is not a legal state-machine move.
        if (values.status !== editing.status) body.status = values.status;
        // ★ Three states: omit the key unless the selection actually changed —
        // its mere presence would raise the whole request to MANAGE_CONFIG and
        // 403 a member who only edited the goal (PLAN §4.1/§4.3).
        if ((values.kb_id ?? "") !== (editing.kb_id ?? "")) {
          body.kb_id = values.kb_id ? values.kb_id : null;
        }
        await projectsApi.update(editing.project_id, body);
        message.success(t("projects.updated"));
        closeCreate();
        // Re-read the server row instead of trusting the local edit (PLAN §3).
        await refresh();
      } else {
        const body: ProjectCreateBody = {
          name: values.name.trim(),
          goal: values.goal?.trim() ?? "",
          status: values.status,
          start_at: startSeconds,
          due_at: dueSeconds,
        };
        const created = await projectsApi.create(body);
        message.success(t("projects.created"));
        closeCreate();
        navigate(`/projects/${created.project_id}`);
      }
    } catch (error) {
      message.error(
        apiErrorMessage(
          error,
          t(editing ? "projects.updateFailed" : "projects.createFailed"),
          t,
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const statusChip = (
    <ChipButton
      icon={<CircleDot size={14} />}
      label={t("projects.status")}
      value={t(STATUS_LABEL_KEYS[status])}
      active={status !== DEFAULT_STATUS}
      ariaLabel={t("projects.chipStatus")}
    >
      <div className={styles.chipMenu}>
        {STATUS_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={option === status}
            className={
              option === status
                ? `${styles.chipOption} ${styles.chipOptionActive}`
                : styles.chipOption
            }
            onClick={() => form.setFieldValue("status", option)}
          >
            <Tag color={STATUS_COLORS[option]}>
              {t(STATUS_LABEL_KEYS[option])}
            </Tag>
          </button>
        ))}
      </div>
    </ChipButton>
  );

  /**
   * Knowledge-base rebind / unbind — the **only** editable entry (PLAN §4.4).
   * Without `MANAGE_CONFIG` the chip is disabled with an explanation instead of
   * letting the user fill it in and eat a 403 (acceptance ②).
   */
  const boundBase = bases.find((base) => base.id === kbId) ?? null;
  const kbChip = (
    <ChipButton
      icon={<BookOpen size={14} />}
      label={t("projects.kbId")}
      value={boundBase ? boundBase.name : null}
      active={kbId !== ""}
      disabled={!canManageConfig}
      ariaLabel={
        canManageConfig ? t("projects.kbId") : t("common.noPermission")
      }
    >
      <div className={styles.chipMenu}>
        {bases.map((base) => (
          <button
            key={base.id}
            type="button"
            aria-pressed={base.id === kbId}
            className={
              base.id === kbId
                ? `${styles.chipOption} ${styles.chipOptionActive}`
                : styles.chipOption
            }
            onClick={() => form.setFieldValue("kb_id", base.id)}
          >
            {base.name}
          </button>
        ))}
        <button
          type="button"
          className={styles.chipOption}
          onClick={() => form.setFieldValue("kb_id", "")}
        >
          {t("projects.kbUnbind")}
        </button>
      </div>
    </ChipButton>
  );

  const dateChip = (
    field: "start_at" | "due_at",
    label: string,
    ariaLabel: string,
    icon: JSX.Element,
    value: Dayjs | null | undefined,
  ) => (
    <ChipButton
      icon={icon}
      label={label}
      value={value ? value.format(DATE_FORMAT) : null}
      active={Boolean(value)}
      ariaLabel={ariaLabel}
    >
      <div className={styles.chipPopover}>
        <DatePicker
          showTime={{ format: "HH:mm" }}
          format={DATE_FORMAT}
          className={styles.field}
          value={value ?? null}
          onChange={(next) => form.setFieldValue(field, next)}
          aria-label={ariaLabel}
        />
      </div>
    </ChipButton>
  );

  return (
    <PageShell
      title={t("projects.title")}
      subtitle={t("projects.subtitle")}
      actions={
        <>
          <Tooltip title={t("common.refresh")}>
            <Button
              icon={<RefreshCw size={15} />}
              loading={loading}
              onClick={() => void refresh()}
            />
          </Tooltip>
          <Button type="primary" icon={<Plus size={15} />} onClick={openCreate}>
            {t("projects.create")}
          </Button>
        </>
      }
    >
      {loading && projects.length === 0 ? (
        <div className={styles.centered}>
          <Spin />
        </div>
      ) : projects.length === 0 ? (
        <EmptyState
          variant="mascot"
          title={t("projects.empty")}
          description={t("projects.emptyDesc")}
          actionLabel={t("projects.create")}
          onAction={openCreate}
        />
      ) : (
        <List
          className={styles.list}
          dataSource={projects}
          rowKey="project_id"
          renderItem={(project) => (
            <List.Item
              className={
                project.status === "archived" ? styles.rowArchived : undefined
              }
              onClick={() => navigate(`/projects/${project.project_id}`)}
            >
              <div className={styles.row}>
                <div className={styles.rowIcon}>
                  <FolderKanban size={18} strokeWidth={1.8} />
                </div>
                <div className={styles.rowBody}>
                  <div className={styles.rowTitle}>
                    <span className={styles.name}>{project.name}</span>
                    <Tag color={STATUS_COLORS[project.status]}>
                      {t(STATUS_LABEL_KEYS[project.status])}
                    </Tag>
                  </div>
                  <div className={styles.rowGoal}>
                    {project.goal || t("projects.noGoal")}
                  </div>
                  <div className={styles.rowMeta}>
                    <span>
                      {t("projects.dueAt")}
                      {": "}
                      {formatServerDateTime(project.due_at ?? 0, timeZone)}
                    </span>
                    <span>
                      {t("projects.updatedAt")}
                      {": "}
                      {formatServerDateTime(project.updated_at, timeZone)}
                    </span>
                  </div>
                </div>
                {project.status === "archived" ? null : (
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <Tooltip title={t("common.edit")}>
                      <Button
                        type="text"
                        size="small"
                        aria-label={t("common.edit")}
                        icon={<Pencil size={14} />}
                        onClick={(event) => {
                          // The row itself navigates; the button must not.
                          event.stopPropagation();
                          openEdit(project);
                        }}
                      />
                    </Tooltip>
                  </div>
                )}
              </div>
            </List.Item>
          )}
        />
      )}

      <Modal
        open={createOpen}
        title={
          <span
            className={styles.breadcrumb}
            data-testid="create-project-breadcrumb"
          >
            {t("projects.title")} ›{" "}
            {t(editing ? "projects.update" : "projects.create")}
          </span>
        }
        okText={editing ? t("common.save") : t("common.create")}
        cancelText={t("common.cancel")}
        confirmLoading={saving}
        destroyOnHidden
        onOk={() => form.submit()}
        onCancel={closeCreate}
      >
        <div className={styles.dialog} data-testid="create-project-dialog">
          <Form<ProjectFormValues>
            form={form}
            layout="vertical"
            onFinish={(values) => void submitForm(values)}
          >
            {/* Field 1 — inline title, no label box (screenshot alignment). */}
            <div data-testid="create-project-field-name">
              <Form.Item
                name="name"
                rules={[
                  { required: true, message: t("projects.nameRequired") },
                ]}
              >
                <Input
                  className={styles.titleInput}
                  placeholder={t("projects.namePlaceholder")}
                  maxLength={120}
                  data-testid="create-project-name"
                />
              </Form.Item>
            </div>
            {/* Field 2 — description. */}
            <div data-testid="create-project-field-goal">
              <Form.Item name="goal">
                <Input.TextArea
                  autoSize={{ minRows: 2, maxRows: 5 }}
                  placeholder={t("projects.goalPlaceholder")}
                  data-testid="create-project-goal"
                />
              </Form.Item>
            </div>
            {/* Registered fields: ``onFinish`` only returns *registered* ones, so
                the chip-backed values need a hidden input. An unregistered
                ``kb_id`` reads as "unchanged" and would silently unbind the
                project's base on any other edit. */}
            <Form.Item name="status" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="kb_id" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="start_at" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="due_at" hidden>
              <Input />
            </Form.Item>
            <ChipToolbar testId="create-project-chips">
              {/* Field 3 — status chip (six options; PLAN §3.2 semantics). */}
              <span data-testid="create-project-field-status">
                {statusChip}
              </span>
              {/* Fields 4 and 5 — start / due date chips. */}
              <span data-testid="create-project-field-start">
                {dateChip(
                  "start_at",
                  t("projects.startAt"),
                  t("projects.chipStartAt"),
                  <CalendarDays size={14} />,
                  startAt,
                )}
              </span>
              <span data-testid="create-project-field-due">
                {dateChip(
                  "due_at",
                  t("projects.dueAt"),
                  t("projects.chipDueAt"),
                  <CalendarClock size={14} />,
                  dueAt,
                )}
              </span>
              {editing ? (
                <span data-testid="create-project-field-kb">{kbChip}</span>
              ) : null}
            </ChipToolbar>
            {editing && !canManageConfig ? (
              <div
                className={styles.readOnlyHint}
                data-testid="kb-readonly-hint"
              >
                {t("common.noPermission")}
              </div>
            ) : null}
            {status === "archived" ? (
              <div
                className={styles.readOnlyHint}
                data-testid="create-project-archived-hint"
              >
                {t("projects.archiveConfirmDesc")}
              </div>
            ) : null}
          </Form>
        </div>
      </Modal>
    </PageShell>
  );
}

export default ProjectsPage;
