import { useState } from "react";
import {
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { projectMetadataApi } from "../../../api/modules/projectMetadata";
import type {
  ProjectCustomFieldDefinition,
  ProjectCustomFieldType,
} from "../../../api/modules/projects";
import { EmptyState } from "../../../components/EmptyState";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "../../../utils/antdMessage";
import { showConfirmModal } from "../../../utils/confirmModal";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./CustomFieldsPanel.module.less";

/**
 * Custom-field definition manager — the display side of ring ④ for field
 * *definitions* (PLAN §6.4); the per-task values are rendered by the task
 * dialog and the board card (T-FE-MODAL).
 *
 * Contract (PLAN §6.3): the create body is
 * ``{key,label,type,required,options,sort_order}``; the update body is
 * ``{label,required,options,sort_order}`` — ``type`` / ``key`` are immutable
 * server-side and therefore read-only here. All copy comes from the frozen key
 * table (PLAN §13.1); no string is hard-coded.
 */

const CF_TYPE_LABEL_KEYS: Record<ProjectCustomFieldType, string> = {
  text: "projects.cfTypeText",
  number: "projects.cfTypeNumber",
  date: "projects.cfTypeDate",
  select: "projects.cfTypeSelect",
};

const CF_TYPES = Object.keys(CF_TYPE_LABEL_KEYS) as ProjectCustomFieldType[];

/** Mirrors PLAN §6.2 for pre-submit feedback (the server stays authoritative). */
const CF_KEY_PATTERN = /^[a-z][a-z0-9_]{0,31}$/;
const CF_MAX_LABEL_LENGTH = 64;
const CF_MAX_OPTIONS = 50;
const CF_MAX_OPTION_LENGTH = 64;

interface FieldFormValues {
  key: string;
  label: string;
  type: ProjectCustomFieldType;
  required: boolean;
  options: string[];
}

function emptyFieldValues(): FieldFormValues {
  return { key: "", label: "", type: "text", required: false, options: [] };
}

export interface CustomFieldsPanelProps {
  projectId: string;
  /** Managing definitions needs ``PROJECT_WRITE``; viewers get a read-only list. */
  canEdit: boolean;
}

/** Trim, drop blanks and de-duplicate (PLAN §6.2 requires unique non-empties). */
function normalizeOptions(options: string[] | undefined): string[] {
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const raw of options ?? []) {
    const option = String(raw).trim();
    if (!option || seen.has(option)) continue;
    seen.add(option);
    cleaned.push(option);
  }
  return cleaned;
}

/** ``select`` needs a non-empty option set; every other type stores ``[]``. */
function optionsFor(values: FieldFormValues): string[] {
  return values.type === "select" ? normalizeOptions(values.options) : [];
}

export function CustomFieldsPanel({
  projectId,
  canEdit,
}: CustomFieldsPanelProps) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [form] = Form.useForm<FieldFormValues>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectCustomFieldDefinition | null>(
    null,
  );
  const [saving, setSaving] = useState(false);

  const {
    data: definitions,
    loading,
    refresh,
  } = useAsyncResource<ProjectCustomFieldDefinition[]>(
    [],
    () => projectMetadataApi.listCustomFields(projectId),
    [projectId],
    {
      t,
      errorFallback: t("projects.loadFailed"),
      logLabel: "project-custom-fields",
    },
  );

  /**
   * Seed the store per open: rc-field-form keeps what a previous open left in
   * it (``initialValues`` are merged *under* the store), so an explicit
   * ``setFieldsValue`` is the only single-source reset that works.
   */
  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(emptyFieldValues());
    setModalOpen(true);
  };

  const openEdit = (field: ProjectCustomFieldDefinition) => {
    setEditing(field);
    form.setFieldsValue({
      key: field.key,
      label: field.label,
      type: field.type,
      required: field.required,
      options: field.options,
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
  };

  const submit = async (values: FieldFormValues) => {
    setSaving(true);
    try {
      if (editing) {
        await projectMetadataApi.updateCustomField(
          projectId,
          editing.field_id,
          {
            label: values.label.trim(),
            required: values.required,
            options: optionsFor(values),
            sort_order: editing.sort_order,
          },
        );
      } else {
        await projectMetadataApi.createCustomField(projectId, {
          key: values.key.trim(),
          label: values.label.trim(),
          type: values.type,
          required: values.required,
          options: optionsFor(values),
          sort_order: definitions.length,
        });
      }
      setModalOpen(false);
      await refresh();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.cfInvalid"), t));
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = (field: ProjectCustomFieldDefinition) => {
    showConfirmModal({
      title: t("projects.cfDeleteConfirm"),
      okText: t("common.delete"),
      okType: "danger",
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await projectMetadataApi.deleteCustomField(projectId, field.field_id);
          await refresh();
        } catch (error) {
          message.error(apiErrorMessage(error, t("projects.cfInvalid"), t));
        }
      },
    });
  };

  const columns: ColumnsType<ProjectCustomFieldDefinition> = [
    {
      title: t("projects.cfLabel"),
      dataIndex: "label",
      key: "label",
    },
    {
      title: t("projects.cfKey"),
      dataIndex: "key",
      key: "key",
      width: 160,
      render: (key: string) => <span className={styles.mono}>{key}</span>,
    },
    {
      title: t("projects.cfType"),
      dataIndex: "type",
      key: "type",
      width: 100,
      render: (type: ProjectCustomFieldType) => t(CF_TYPE_LABEL_KEYS[type]),
    },
    {
      title: t("projects.cfRequired"),
      dataIndex: "required",
      key: "required",
      width: 90,
      render: (required: boolean) =>
        required ? (
          <Tag color="red">{t("projects.cfRequired")}</Tag>
        ) : (
          <span className={styles.dash}>—</span>
        ),
    },
    {
      title: t("projects.cfOptions"),
      dataIndex: "options",
      key: "options",
      render: (options: string[]) =>
        options.length ? (
          <Space size={4} wrap>
            {options.map((option) => (
              <Tag key={option}>{option}</Tag>
            ))}
          </Space>
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
      render: (_, field) => (
        <div className={styles.actions}>
          <Tooltip title={t("common.edit")}>
            <Button
              type="text"
              size="small"
              aria-label={t("common.edit")}
              icon={<Pencil size={14} />}
              onClick={() => openEdit(field)}
            />
          </Tooltip>
          <Tooltip title={t("common.delete")}>
            <Button
              type="text"
              size="small"
              danger
              aria-label={t("common.delete")}
              icon={<Trash2 size={14} />}
              onClick={() => confirmDelete(field)}
            />
          </Tooltip>
        </div>
      ),
    });
  }

  return (
    <section className={styles.section} data-testid="project-custom-fields">
      <div className={styles.sectionTitle}>
        {t("projects.customFieldsTitle")}
        {canEdit ? (
          <span className={styles.headerActions}>
            <Button
              size="small"
              type="primary"
              icon={<Plus size={14} />}
              onClick={openCreate}
            >
              {t("projects.cfAdd")}
            </Button>
          </span>
        ) : null}
      </div>

      {definitions.length === 0 && !loading ? (
        <div className={styles.empty} data-testid="custom-fields-empty">
          <EmptyState variant="empty" title={t("projects.cfEmpty")} />
        </div>
      ) : (
        <Table<ProjectCustomFieldDefinition>
          rowKey="field_id"
          size="small"
          className={styles.table}
          loading={loading}
          columns={columns}
          dataSource={definitions}
          pagination={false}
          scroll={{ x: 820 }}
        />
      )}

      <Modal
        open={modalOpen}
        title={editing ? t("common.edit") : t("projects.cfAdd")}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        confirmLoading={saving}
        destroyOnHidden
        onOk={() => form.submit()}
        onCancel={closeModal}
      >
        <Form<FieldFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => void submit(values)}
        >
          <Form.Item
            name="key"
            label={t("projects.cfKey")}
            rules={[
              { required: true, message: t("projects.cfInvalid") },
              { pattern: CF_KEY_PATTERN, message: t("projects.cfInvalid") },
            ]}
          >
            <Input
              className={styles.field}
              disabled={editing !== null}
              maxLength={32}
            />
          </Form.Item>
          <Form.Item
            name="label"
            label={t("projects.cfLabel")}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t("projects.cfInvalid"),
              },
              { max: CF_MAX_LABEL_LENGTH, message: t("projects.cfInvalid") },
            ]}
          >
            <Input className={styles.field} maxLength={CF_MAX_LABEL_LENGTH} />
          </Form.Item>
          <Form.Item name="type" label={t("projects.cfType")}>
            <Select<ProjectCustomFieldType>
              className={styles.field}
              disabled={editing !== null}
              options={CF_TYPES.map((type) => ({
                value: type,
                label: t(CF_TYPE_LABEL_KEYS[type]),
              }))}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev: FieldFormValues, next: FieldFormValues) =>
              prev.type !== next.type
            }
          >
            {({ getFieldValue }) =>
              getFieldValue("type") === "select" ? (
                <Form.Item
                  name="options"
                  label={t("projects.cfOptions")}
                  rules={[
                    {
                      validator: async (_rule, value: string[] | undefined) => {
                        const cleaned = normalizeOptions(value);
                        if (
                          cleaned.length === 0 ||
                          cleaned.length > CF_MAX_OPTIONS ||
                          cleaned.some(
                            (option) => option.length > CF_MAX_OPTION_LENGTH,
                          )
                        ) {
                          throw new Error(t("projects.cfInvalid"));
                        }
                      },
                    },
                  ]}
                >
                  <Select
                    className={styles.field}
                    mode="tags"
                    open={false}
                    suffixIcon={null}
                    tokenSeparators={[","]}
                  />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item
            name="required"
            label={t("projects.cfRequired")}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}

export default CustomFieldsPanel;
