/**
 * createAtom — modal for manually adding an Entity + AtomCard.
 */
import { useEffect } from "react";
import { Form, Input, Modal, Radio, Select } from "antd";
import { message } from "@/utils/antdMessage";
import { useTranslation } from "react-i18next";

import {
  memoryDashboardApi,
  type AtomItem,
  type AtomKind,
  type EntityItem,
} from "../../../../api/modules/memoryDashboard";

const KIND_OPTIONS: { value: AtomKind; label: string }[] = [
  { value: "Fact", label: "事实" },
  { value: "Preference", label: "偏好" },
  { value: "Decision", label: "决定" },
  { value: "Task", label: "任务" },
];

const ENTITY_TYPE_OPTIONS = [
  { value: "Fact", label: "事实" },
  { value: "Person", label: "人物" },
  { value: "User", label: "用户" },
  { value: "Project", label: "项目" },
  { value: "Decision", label: "决定" },
  { value: "Task", label: "任务" },
];

interface Props {
  open: boolean;
  agentId: string;
  entities: EntityItem[];
  /** When set, lock the form to this existing topic. */
  presetEntityId?: string;
  onClose: () => void;
  onSuccess?: (
    atom: AtomItem,
    entity: EntityItem,
    createdEntity: boolean,
  ) => void;
}

export default function CreateAtomModal({
  open,
  agentId,
  entities,
  presetEntityId,
  onClose,
  onSuccess,
}: Props) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const topicMode = Form.useWatch("topicMode", form) as
    | "existing"
    | "new"
    | undefined;

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      topicMode: presetEntityId || entities.length > 0 ? "existing" : "new",
      entity_id: presetEntityId,
      entity_name: undefined,
      entity_type: "Fact",
      kind: "Fact",
      assertion: "",
    });
  }, [open, presetEntityId, entities.length, form]);

  const lockedToEntity = Boolean(presetEntityId);

  return (
    <Modal
      title={
        lockedToEntity
          ? t("memory.create.titleInTopic", "在此主题下添加记忆")
          : t("memory.create.title", "新建记忆")
      }
      open={open}
      onCancel={onClose}
      okText={t("memory.create.ok", "保存")}
      cancelText={t("common.cancel", "取消")}
      destroyOnHidden
      onOk={async () => {
        const values = await form.validateFields();
        const assertion = String(values.assertion || "").trim();
        try {
          const body =
            values.topicMode === "new"
              ? {
                  assertion,
                  entity_name: String(values.entity_name || "").trim(),
                  entity_type: values.entity_type as string,
                  kind: values.kind as AtomKind,
                }
              : {
                  assertion,
                  entity_id: values.entity_id as string,
                  kind: values.kind as AtomKind,
                };
          const r = await memoryDashboardApi.createAtom(agentId, body);
          message.success(t("memory.create.success", "记忆已添加"));
          onSuccess?.(r.atom, r.entity, r.created_entity);
          onClose();
        } catch (e) {
          message.error(
            t("memory.create.failed", {
              message: (e as Error).message ?? e,
              defaultValue: "添加失败：{{message}}",
            }),
          );
          throw e;
        }
      }}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        {!lockedToEntity ? (
          <Form.Item name="topicMode" label={t("memory.create.topic", "主题")}>
            <Radio.Group>
              <Radio.Button value="existing" disabled={entities.length === 0}>
                {t("memory.create.existingTopic", "已有主题")}
              </Radio.Button>
              <Radio.Button value="new">
                {t("memory.create.newTopic", "新建主题")}
              </Radio.Button>
            </Radio.Group>
          </Form.Item>
        ) : null}

        {lockedToEntity || topicMode === "existing" ? (
          <Form.Item
            name="entity_id"
            label={
              lockedToEntity
                ? undefined
                : t("memory.create.pickTopic", "选择主题")
            }
            rules={
              lockedToEntity
                ? []
                : [
                    {
                      required: true,
                      message: t("memory.create.topicRequired", "请选择主题"),
                    },
                  ]
            }
            hidden={lockedToEntity}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={entities.map((e) => ({
                value: e.id,
                label: e.canonical_name,
              }))}
            />
          </Form.Item>
        ) : (
          <>
            <Form.Item
              name="entity_name"
              label={t("memory.create.topicName", "主题名称")}
              rules={[
                {
                  required: true,
                  message: t(
                    "memory.create.topicNameRequired",
                    "请填写主题名称",
                  ),
                },
              ]}
            >
              <Input
                placeholder={t(
                  "memory.create.topicNamePlaceholder",
                  "例如：饮品偏好",
                )}
              />
            </Form.Item>
            <Form.Item
              name="entity_type"
              label={t("memory.create.topicType", "主题类型")}
            >
              <Select options={ENTITY_TYPE_OPTIONS} />
            </Form.Item>
          </>
        )}

        <Form.Item name="kind" label={t("memory.create.kind", "记忆类型")}>
          <Select options={KIND_OPTIONS} />
        </Form.Item>
        <Form.Item
          name="assertion"
          label={t("memory.create.assertion", "记忆内容")}
          rules={[
            {
              required: true,
              message: t("memory.create.assertionRequired", "请填写记忆内容"),
            },
          ]}
        >
          <Input.TextArea
            rows={4}
            placeholder={t(
              "memory.create.assertionPlaceholder",
              "例如：喜欢喝美式咖啡",
            )}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
