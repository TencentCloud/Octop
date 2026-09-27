import { useState } from "react";
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
import type { Dayjs } from "dayjs";
import {
  CalendarClock,
  CalendarDays,
  CircleDot,
  FolderKanban,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  projectsApi,
  type ProjectCreateBody,
  type ProjectOut,
  type ProjectStatus,
} from "../../api/modules/projects";
import { ChipButton, ChipToolbar } from "../../components/ChipToolbar";
import { EmptyState } from "../../components/EmptyState";
import { useAsyncResource } from "../../hooks/useAsyncResource";
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
  };
}

interface ProjectFormValues {
  name: string;
  goal?: string;
  status: ProjectStatus;
  start_at?: Dayjs | null;
  due_at?: Dayjs | null;
}

/**
 * R4: the dialog field set is exactly name / goal / status / start / due. The
 * status is sent along, so the request body is ``ProjectCreateBody`` plus
 * ``status`` — never priority / owner / repository.
 */
type ProjectCreateRequest = ProjectCreateBody & { status: ProjectStatus };

function ProjectsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const timeZone = useServerTimezone();
  const [form] = Form.useForm<ProjectFormValues>();
  const [createOpen, setCreateOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const status = Form.useWatch("status", form) ?? DEFAULT_STATUS;
  const startAt = Form.useWatch("start_at", form);
  const dueAt = Form.useWatch("due_at", form);

  const {
    data: projects,
    loading,
    refresh,
  } = useAsyncResource<ProjectOut[]>([], () => projectsApi.list(), [], {
    t,
    errorFallback: t("projects.loadFailed"),
    logLabel: "projects",
  });

  /**
   * Seed the form store before the modal mounts. ``initialValues`` cannot do
   * this: rc-field-form merges them *under* whatever the store already holds,
   * so a reopened dialog would keep the previous entry.
   */
  const openCreate = () => {
    form.setFieldsValue(emptyValues());
    setCreateOpen(true);
  };

  const closeCreate = () => {
    setCreateOpen(false);
  };

  const submitCreate = async (values: ProjectFormValues) => {
    const body: ProjectCreateRequest = {
      name: values.name.trim(),
      goal: values.goal?.trim() ?? "",
      status: values.status,
      start_at: values.start_at ? values.start_at.unix() : null,
      due_at: values.due_at ? values.due_at.unix() : null,
    };
    setSaving(true);
    try {
      const created = await projectsApi.create(body);
      message.success(t("projects.created"));
      closeCreate();
      navigate(`/projects/${created.project_id}`);
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.createFailed"), t));
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
        <Form.Item name={field} noStyle>
          <DatePicker
            showTime={{ format: "HH:mm" }}
            format={DATE_FORMAT}
            className={styles.field}
          />
        </Form.Item>
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
            {t("projects.title")} › {t("projects.create")}
          </span>
        }
        okText={t("common.create")}
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
            onFinish={(values) => void submitCreate(values)}
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
            {/* Registered so the chip's value is part of the submitted form. */}
            <Form.Item name="status" hidden>
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
            </ChipToolbar>
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
