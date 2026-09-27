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
import { FolderKanban, Plus, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  projectsApi,
  type ProjectCreateBody,
  type ProjectOut,
  type ProjectStatus,
} from "../../api/modules/projects";
import { EmptyState } from "../../components/EmptyState";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useServerTimezone } from "../../hooks/useServerTimezone";
import PageShell from "../../layouts/PageShell";
import { apiErrorMessage } from "../../utils/apiError";
import { message } from "../../utils/antdMessage";
import { formatServerDateTime } from "../../utils/formatMessageTime";
import styles from "./index.module.less";

const STATUS_LABEL_KEYS: Record<ProjectStatus, string> = {
  draft: "projects.statusDraft",
  active: "projects.statusActive",
  paused: "projects.statusPaused",
  archived: "projects.statusArchived",
};

const STATUS_COLORS: Record<ProjectStatus, string> = {
  draft: "default",
  active: "success",
  paused: "warning",
  archived: "default",
};

interface ProjectFormValues {
  name: string;
  goal?: string;
  start_at?: Dayjs | null;
  due_at?: Dayjs | null;
}

function ProjectsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const timeZone = useServerTimezone();
  const [form] = Form.useForm<ProjectFormValues>();
  const [createOpen, setCreateOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const {
    data: projects,
    loading,
    refresh,
  } = useAsyncResource<ProjectOut[]>([], () => projectsApi.list(), [], {
    t,
    errorFallback: t("projects.loadFailed"),
    logLabel: "projects",
  });

  const openCreate = () => {
    form.resetFields();
    setCreateOpen(true);
  };

  const closeCreate = () => {
    setCreateOpen(false);
    form.resetFields();
  };

  const submitCreate = async (values: ProjectFormValues) => {
    const body: ProjectCreateBody = {
      name: values.name.trim(),
      goal: values.goal?.trim() ?? "",
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
        title={t("projects.create")}
        okText={t("common.create")}
        cancelText={t("common.cancel")}
        confirmLoading={saving}
        destroyOnHidden
        onOk={() => form.submit()}
        onCancel={closeCreate}
      >
        <Form<ProjectFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => void submitCreate(values)}
        >
          <Form.Item
            name="name"
            label={t("projects.name")}
            rules={[{ required: true, message: t("projects.nameRequired") }]}
          >
            <Input
              className={styles.field}
              placeholder={t("projects.namePlaceholder")}
              maxLength={120}
            />
          </Form.Item>
          <Form.Item name="goal" label={t("projects.goal")}>
            <Input.TextArea
              rows={3}
              placeholder={t("projects.goalPlaceholder")}
            />
          </Form.Item>
          <Form.Item name="start_at" label={t("projects.startAt")}>
            <DatePicker
              className={styles.field}
              showTime={{ format: "HH:mm" }}
              format="YYYY-MM-DD HH:mm"
            />
          </Form.Item>
          <Form.Item name="due_at" label={t("projects.dueAt")}>
            <DatePicker
              className={styles.field}
              showTime={{ format: "HH:mm" }}
              format="YYYY-MM-DD HH:mm"
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

export default ProjectsPage;
