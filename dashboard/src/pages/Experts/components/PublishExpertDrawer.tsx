import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Button, Drawer, Form, Input, Spin, Switch } from "antd";
import { message } from "@/utils/antdMessage";

import { agentChatApi } from "../../../api/modules/agentChat";
import {
  publishedExpertsApi,
  type PublishedExpert,
  type PublishExpertBody,
} from "../../../api/modules/publishedExperts";
import type { OctopAgent } from "../../../context/AgentContext";
import { apiErrorMessage } from "../../../utils/apiError";
import { pickLocale } from "../../../utils/localizedText";
import styles from "../index.module.less";

export interface PublishExpertDrawerProps {
  open: boolean;
  mode: "publish" | "refresh";
  agent: OctopAgent;
  published: PublishedExpert | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface PublishFormValues {
  name: string;
  description?: string;
  welcome_zh?: string;
  welcome_en?: string;
  allow_skill_details?: boolean;
}

export default function PublishExpertDrawer({
  open,
  mode,
  agent,
  published,
  onClose,
  onSuccess,
}: PublishExpertDrawerProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<PublishFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [prefillLoading, setPrefillLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    const loadDefaults = async () => {
      setPrefillLoading(true);
      const baseName =
        mode === "refresh" && published ? published.name : agent.name;
      const baseDescription =
        mode === "refresh" && published
          ? published.description
          : agent.description || "";

      try {
        const welcome = await agentChatApi.welcome(agent.agent_id);
        if (cancelled) return;
        form.setFieldsValue({
          name: baseName,
          description: baseDescription,
          welcome_zh: pickLocale(welcome.welcome_message, "zh"),
          welcome_en: pickLocale(welcome.welcome_message, "en"),
          allow_skill_details:
            mode === "refresh" && published
              ? published.allow_skill_details !== false
              : true,
        });
      } catch {
        if (cancelled) return;
        form.setFieldsValue({
          name: baseName,
          description: baseDescription,
          welcome_zh: "",
          welcome_en: "",
          allow_skill_details:
            mode === "refresh" && published
              ? published.allow_skill_details !== false
              : true,
        });
      } finally {
        if (!cancelled) setPrefillLoading(false);
      }
    };

    void loadDefaults();
    return () => {
      cancelled = true;
    };
  }, [open, mode, agent, published, form]);

  const buildBody = (values: PublishFormValues): PublishExpertBody => ({
    name: values.name.trim(),
    description: values.description?.trim() || "",
    welcome_message: {
      zh: values.welcome_zh?.trim() || "",
      en: values.welcome_en?.trim() || "",
    },
    allow_skill_details: values.allow_skill_details !== false,
  });

  const handleSubmit = async () => {
    let values: PublishFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    setSubmitting(true);
    try {
      const body = buildBody(values);
      if (mode === "refresh" && published) {
        await publishedExpertsApi.refresh(published.id, body);
        message.success(t("experts.published.updateSuccess"));
      } else {
        await publishedExpertsApi.publish(agent.agent_id, body);
        message.success(t("experts.published.publishSuccessHint"));
      }
      onSuccess();
      onClose();
    } catch (err) {
      message.error(
        apiErrorMessage(
          err,
          mode === "refresh"
            ? t("experts.published.updateFailed")
            : t("experts.published.publishFailed"),
          t,
        ),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const primaryLabel =
    mode === "refresh"
      ? t("experts.published.update")
      : t("experts.published.publish");

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={440}
      destroyOnHidden
      maskClosable={!submitting}
      closable={!submitting}
      title={
        mode === "refresh"
          ? t("experts.published.update")
          : t("experts.published.drawerTitle")
      }
      footer={
        <div className={styles.publishDrawerFooter}>
          <Button onClick={onClose} disabled={submitting}>
            {t("common.cancel")}
          </Button>
          <Button
            type="primary"
            loading={submitting}
            disabled={prefillLoading}
            onClick={() => void handleSubmit()}
          >
            {primaryLabel}
          </Button>
        </div>
      }
    >
      <div className={styles.publishDrawerBody}>
        {prefillLoading ? (
          <div className={styles.publishDrawerLoading}>
            <Spin size="small" />
          </div>
        ) : null}

        <Alert
          type="info"
          showIcon
          className={styles.publishDrawerHint}
          message={t("experts.published.drawerHint")}
        />

        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          disabled={prefillLoading || submitting}
        >
          <Form.Item
            name="name"
            label={t("experts.published.fieldName")}
            rules={[
              {
                required: true,
                message: t("experts.pleaseEnterName"),
              },
            ]}
          >
            <Input placeholder={t("experts.agentNameLabel")} />
          </Form.Item>
          <Form.Item
            name="description"
            label={t("experts.published.fieldDescription")}
          >
            <Input.TextArea
              rows={3}
              placeholder={t("experts.table.description")}
            />
          </Form.Item>
          <Form.Item
            name="welcome_zh"
            label={t("experts.published.fieldWelcomeZh")}
          >
            <Input.TextArea
              rows={2}
              placeholder={t("experts.published.fieldWelcomePlaceholder")}
            />
          </Form.Item>
          <Form.Item
            name="welcome_en"
            label={t("experts.published.fieldWelcomeEn")}
          >
            <Input.TextArea
              rows={2}
              placeholder={t("experts.published.fieldWelcomePlaceholder")}
            />
          </Form.Item>
          <Form.Item
            name="allow_skill_details"
            label={t("experts.published.fieldAllowSkillDetails")}
            valuePropName="checked"
            extra={t("experts.published.allowSkillDetailsHint")}
          >
            <Switch />
          </Form.Item>
        </Form>
      </div>
    </Drawer>
  );
}
