import { useState } from "react";
import { Button, Form, Input, Modal, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { projectMetadataApi } from "../../../api/modules/projectMetadata";
import type { ProjectTagDefinition } from "../../../api/modules/projects";
import { EmptyState } from "../../../components/EmptyState";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "../../../utils/antdMessage";
import { showConfirmModal } from "../../../utils/confirmModal";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./CustomFieldsPanel.module.less";

/**
 * Tag definition manager (PLAN §4). Definitions are project-scoped; deleting one
 * cascades to the task↔tag rows server-side, which the confirm dialog states.
 * Copy comes from the frozen key table (PLAN §13.1) only.
 */

/** ``color`` is ``''`` or ``#RRGGBB`` — mirrors PLAN §4 for early feedback. */
const TAG_COLOR_PATTERN = /^#[0-9a-fA-F]{6}$/;
const TAG_MAX_NAME_LENGTH = 32;

interface TagFormValues {
  name: string;
  color: string;
}

export interface TagsManagerProps {
  projectId: string;
  /** Managing tags needs ``PROJECT_WRITE``; viewers get a read-only list. */
  canEdit: boolean;
}

export function TagsManager({ projectId, canEdit }: TagsManagerProps) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [form] = Form.useForm<TagFormValues>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectTagDefinition | null>(null);
  const [saving, setSaving] = useState(false);

  const {
    data: tags,
    loading,
    refresh,
  } = useAsyncResource<ProjectTagDefinition[]>(
    [],
    () => projectMetadataApi.listTags(projectId),
    [projectId],
    {
      t,
      errorFallback: t("projects.loadFailed"),
      logLabel: "project-tags",
    },
  );

  // See CustomFieldsPanel: seed the store per open instead of ``initialValues``.
  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({ name: "", color: "" });
    setModalOpen(true);
  };

  const openEdit = (tag: ProjectTagDefinition) => {
    setEditing(tag);
    form.setFieldsValue({ name: tag.name, color: tag.color });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
  };

  const submit = async (values: TagFormValues) => {
    const body = {
      name: values.name.trim(),
      color: (values.color ?? "").trim().toLowerCase(),
    };
    setSaving(true);
    try {
      if (editing) {
        await projectMetadataApi.updateTag(projectId, editing.tag_id, body);
      } else {
        await projectMetadataApi.createTag(projectId, body);
      }
      setModalOpen(false);
      await refresh();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.tagInvalid"), t));
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = (tag: ProjectTagDefinition) => {
    showConfirmModal({
      title: t("projects.tagDeleteConfirm"),
      okText: t("common.delete"),
      okType: "danger",
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await projectMetadataApi.deleteTag(projectId, tag.tag_id);
          await refresh();
        } catch (error) {
          message.error(apiErrorMessage(error, t("projects.tagInvalid"), t));
        }
      },
    });
  };

  const columns: ColumnsType<ProjectTagDefinition> = [
    {
      title: t("projects.tagName"),
      dataIndex: "name",
      key: "name",
      render: (name: string, tag) => (
        <Tag color={tag.color || undefined}>{name}</Tag>
      ),
    },
    {
      title: t("projects.tagColor"),
      dataIndex: "color",
      key: "color",
      width: 140,
      render: (color: string) =>
        color ? (
          <span className={styles.colorValue}>{color}</span>
        ) : (
          <span className={styles.dash}>—</span>
        ),
    },
    {
      title: t("projects.createdAt"),
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (createdAt: number) => formatServerDateTime(createdAt, timeZone),
    },
  ];

  if (canEdit) {
    columns.push({
      title: t("common.actions"),
      key: "actions",
      width: 90,
      align: "right",
      render: (_, tag) => (
        <div className={styles.actions}>
          <Tooltip title={t("common.edit")}>
            <Button
              type="text"
              size="small"
              aria-label={t("common.edit")}
              icon={<Pencil size={14} />}
              onClick={() => openEdit(tag)}
            />
          </Tooltip>
          <Tooltip title={t("common.delete")}>
            <Button
              type="text"
              size="small"
              danger
              aria-label={t("common.delete")}
              icon={<Trash2 size={14} />}
              onClick={() => confirmDelete(tag)}
            />
          </Tooltip>
        </div>
      ),
    });
  }

  return (
    <section className={styles.section} data-testid="project-tags">
      <div className={styles.sectionTitle}>
        {t("projects.tagsTitle")}
        {canEdit ? (
          <span className={styles.headerActions}>
            <Button
              size="small"
              type="primary"
              icon={<Plus size={14} />}
              onClick={openCreate}
            >
              {t("projects.tagCreate")}
            </Button>
          </span>
        ) : null}
      </div>

      {tags.length === 0 && !loading ? (
        <div className={styles.empty} data-testid="tags-empty">
          <EmptyState variant="empty" title={t("projects.tagsEmpty")} />
        </div>
      ) : (
        <Table<ProjectTagDefinition>
          rowKey="tag_id"
          size="small"
          className={styles.table}
          loading={loading}
          columns={columns}
          dataSource={tags}
          pagination={false}
          scroll={{ x: 560 }}
        />
      )}

      <Modal
        open={modalOpen}
        title={editing ? t("common.edit") : t("projects.tagCreate")}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        confirmLoading={saving}
        destroyOnHidden
        onOk={() => form.submit()}
        onCancel={closeModal}
      >
        <Form<TagFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => void submit(values)}
        >
          <Form.Item
            name="name"
            label={t("projects.tagName")}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t("projects.tagInvalid"),
              },
              { max: TAG_MAX_NAME_LENGTH, message: t("projects.tagInvalid") },
            ]}
          >
            <Input className={styles.field} maxLength={TAG_MAX_NAME_LENGTH} />
          </Form.Item>
          <Form.Item
            name="color"
            label={t("projects.tagColor")}
            rules={[
              {
                validator: async (_rule, value: string | undefined) => {
                  const color = (value ?? "").trim();
                  if (color && !TAG_COLOR_PATTERN.test(color)) {
                    throw new Error(t("projects.tagInvalid"));
                  }
                },
              },
            ]}
          >
            <Input className={styles.field} maxLength={7} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => {
              const color = String(getFieldValue("color") ?? "").trim();
              return TAG_COLOR_PATTERN.test(color) ? (
                <Tag color={color}>{color.toLowerCase()}</Tag>
              ) : null;
            }}
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}

export default TagsManager;
