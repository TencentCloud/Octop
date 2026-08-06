import { useEffect, useMemo, useState } from "react";
import { Alert, Form, Input, Modal, Spin, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";

import {
  customExpertTemplatesApi,
  type CustomExpertPreview,
  type PublishCustomExpertBody,
} from "../../../api/modules/customExpertTemplates";
import type { OctopAgent } from "../../../context/AgentContext";

const { Text } = Typography;

interface PublishExpertTemplateModalProps {
  agent: OctopAgent | null;
  onClose: () => void;
  onPublished?: () => void | Promise<void>;
}

function defaultTemplateId(agent: OctopAgent): string {
  const slug = agent.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  const suffix = agent.agent_id
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .slice(-8);
  return `${slug || "custom-agent"}-${suffix || "template"}`.slice(0, 64);
}

export default function PublishExpertTemplateModal({
  agent,
  onClose,
  onPublished,
}: PublishExpertTemplateModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<PublishCustomExpertBody>();
  const [preview, setPreview] = useState<CustomExpertPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!agent) {
      setPreview(null);
      return;
    }
    form.setFieldsValue({
      template_id: defaultTemplateId(agent),
      label_zh: agent.name,
      label_en: agent.name,
      description_zh: agent.description || "",
      description_en: agent.description || "",
      icon_name: agent.icon_name || "sparkles",
      color: agent.color || "#6366f1",
    });
    let cancelled = false;
    setPreview(null);
    setPreviewLoading(true);
    customExpertTemplatesApi
      .preview(agent.agent_id)
      .then((value) => {
        if (!cancelled) setPreview(value);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        message.error(
          err instanceof Error
            ? err.message
            : t("adminUsers.templatePreviewFailed"),
        );
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agent, form, t]);

  const canPublish = useMemo(
    () => !previewLoading && (preview?.included_files.length ?? 0) > 0,
    [preview, previewLoading],
  );

  const submit = async (values: PublishCustomExpertBody) => {
    if (!agent) return;
    setSubmitting(true);
    try {
      await customExpertTemplatesApi.publish(agent.agent_id, values);
      message.success(t("adminUsers.templatePublishSuccess"));
      onClose();
      await onPublished?.();
    } catch (err: unknown) {
      message.error(
        err instanceof Error
          ? err.message
          : t("adminUsers.templatePublishFailed"),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={t("adminUsers.publishTemplateTitle", { name: agent?.name ?? "" })}
      open={agent !== null}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText={t("adminUsers.publishTemplate")}
      cancelText={t("common.cancel")}
      confirmLoading={submitting}
      okButtonProps={{ disabled: !canPublish }}
      width={680}
      destroyOnHidden
    >
      <Alert
        type="warning"
        showIcon
        message={t("adminUsers.templateGlobalWarning")}
        style={{ marginBottom: 16 }}
      />

      <Spin spinning={previewLoading}>
        <Form<PublishCustomExpertBody>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => void submit(values)}
        >
          <Form.Item
            name="template_id"
            label={t("adminUsers.templateId")}
            rules={[
              { required: true },
              {
                pattern: /^[a-z0-9][a-z0-9-]{0,63}$/,
                message: t("adminUsers.templateIdRule"),
              },
            ]}
          >
            <Input />
          </Form.Item>
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}
          >
            <Form.Item
              name="label_zh"
              label={t("adminUsers.templateLabelZh")}
              rules={[{ required: true }]}
            >
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item
              name="label_en"
              label={t("adminUsers.templateLabelEn")}
              rules={[{ required: true }]}
            >
              <Input maxLength={100} />
            </Form.Item>
          </div>
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}
          >
            <Form.Item
              name="description_zh"
              label={t("adminUsers.templateDescriptionZh")}
            >
              <Input.TextArea rows={2} maxLength={500} />
            </Form.Item>
            <Form.Item
              name="description_en"
              label={t("adminUsers.templateDescriptionEn")}
            >
              <Input.TextArea rows={2} maxLength={500} />
            </Form.Item>
          </div>
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}
          >
            <Form.Item name="icon_name" label={t("adminUsers.templateIcon")}>
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item
              name="color"
              label={t("adminUsers.templateColor")}
              rules={[
                {
                  pattern: /^#[0-9a-fA-F]{6}$/,
                  message: t("adminUsers.templateColorRule"),
                },
              ]}
            >
              <Input maxLength={32} />
            </Form.Item>
          </div>
        </Form>

        <div style={{ marginTop: 4 }}>
          <Text strong>{t("adminUsers.templateIncludedFiles")}</Text>
          <div
            style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}
          >
            {preview?.included_files.map((path) => (
              <Tag key={path}>{path}</Tag>
            ))}
            {preview && preview.included_files.length === 0 && (
              <Text type="secondary">
                {t("adminUsers.templateNoReusableFiles")}
              </Text>
            )}
          </div>
        </div>

        {(preview?.excluded_sensitive_files.length ?? 0) > 0 && (
          <div style={{ marginTop: 16 }}>
            <Text strong type="danger">
              {t("adminUsers.templateExcludedFiles")}
            </Text>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 6,
                marginTop: 8,
              }}
            >
              {preview?.excluded_sensitive_files.map((path) => (
                <Tag color="error" key={path}>
                  {path}
                </Tag>
              ))}
            </div>
          </div>
        )}
        {!!preview?.ignored_file_count && (
          <Text type="secondary" style={{ display: "block", marginTop: 12 }}>
            {t("adminUsers.templateIgnoredFiles", {
              count: preview.ignored_file_count,
            })}
          </Text>
        )}
      </Spin>
    </Modal>
  );
}
