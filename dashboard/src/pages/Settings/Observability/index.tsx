import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Form,
  Input,
  Space,
  Switch,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import { Activity, CheckCircle2, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { observabilityApi } from "../../../api/modules/observability";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import tabStyles from "../AdvancedSettings/tabContent.module.less";

const { Text } = Typography;

/** Langfuse observability settings — embeddable in Advanced Settings tab. */
export function ObservabilitySettingsPanel() {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [secretKeySet, setSecretKeySet] = useState(false);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const cfg = await observabilityApi.getLangfuse();
      setSecretKeySet(cfg.secret_key_set);
      form.setFieldsValue({
        enabled: cfg.enabled,
        public_key: cfg.public_key,
        host: cfg.host,
        secret_key: "",
      });
    } catch (err) {
      message.error(t("observability.loadError"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [form, t]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const handleSave = async () => {
    try {
      setSaving(true);
      const values = await form.validateFields();
      const payload = {
        enabled: Boolean(values.enabled),
        public_key: String(values.public_key || "").trim(),
        host: String(values.host || "").trim(),
        secret_key: values.secret_key ? String(values.secret_key) : null,
      };
      const cfg = await observabilityApi.saveLangfuse(payload);
      setSecretKeySet(cfg.secret_key_set);
      form.setFieldValue("secret_key", "");
      message.success(t("observability.saved"));
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("observability.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    try {
      setTesting(true);
      const values = form.getFieldsValue();
      const result = await observabilityApi.testLangfuse({
        public_key: values.public_key || null,
        host: values.host || null,
        secret_key: values.secret_key || null,
      });
      if (result.ok) {
        message.success(t("observability.testSuccess"));
      } else {
        message.error(result.error || t("observability.testFailed"));
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("observability.testFailed"),
      );
    } finally {
      setTesting(false);
    }
  };

  const enabled = Form.useWatch("enabled", form);

  return (
    <>
      <TabPanelHeader
        icon={<Activity size={22} />}
        title={t("observability.langfuseTitle")}
        description={t("observability.langfuseDesc")}
      />

      {loading ? (
        <Text type="secondary">{t("observability.loading")}</Text>
      ) : (
        <Form form={form} layout="vertical" className={tabStyles.formFields}>
          <Form.Item
            name="enabled"
            label={t("observability.enable")}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          {enabled && (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message={t("observability.hint")}
              />
              <Form.Item
                name="host"
                label={t("observability.host")}
                rules={[
                  { required: true, message: t("observability.hostRequired") },
                ]}
              >
                <Input placeholder="https://cloud.langfuse.com" />
              </Form.Item>
              <Form.Item
                name="public_key"
                label={t("observability.publicKey")}
                rules={[
                  {
                    required: true,
                    message: t("observability.publicKeyRequired"),
                  },
                ]}
              >
                <Input placeholder="pk-lf-..." />
              </Form.Item>
              <Form.Item
                name="secret_key"
                label={t("observability.secretKey")}
                extra={
                  secretKeySet ? (
                    <Text type="secondary">
                      <CheckCircle2 size={12} style={{ marginRight: 4 }} />
                      {t("observability.secretKeySet")}
                    </Text>
                  ) : null
                }
                rules={
                  secretKeySet
                    ? []
                    : [
                        {
                          required: true,
                          message: t("observability.secretKeyRequired"),
                        },
                      ]
                }
              >
                <Input.Password placeholder="sk-lf-..." />
              </Form.Item>
            </>
          )}

          <Space>
            <Button
              type="primary"
              loading={saving}
              onClick={() => void handleSave()}
            >
              {t("common.save")}
            </Button>
            <Button
              loading={testing}
              disabled={!enabled}
              onClick={() => void handleTest()}
            >
              {t("observability.testConnection")}
            </Button>
            <Button
              icon={<RefreshCw size={14} />}
              onClick={() => void fetchConfig()}
            >
              {t("common.refresh")}
            </Button>
          </Space>
        </Form>
      )}
    </>
  );
}

export default ObservabilitySettingsPanel;
