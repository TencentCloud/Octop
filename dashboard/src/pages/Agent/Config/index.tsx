import { useState, useEffect } from "react";
import { Form, InputNumber, Button, Card } from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import api from "../../../api";
import styles from "./index.module.less";
import type { AgentsRunningConfig } from "../../../api/types";

function AgentConfigPage() {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const config = await api.getAgentRunningConfig();
      // API may return camelCase keys (maxIters, maxInputLength) due to
      // Pydantic alias serialization; normalise to snake_case for the form.
      const raw = config as unknown as Record<string, unknown>;
      form.setFieldsValue({
        max_iters: raw.max_iters ?? raw.maxIters,
        max_input_length: raw.max_input_length ?? raw.maxInputLength,
      });
    } catch (err) {
      const errMsg =
        err instanceof Error ? err.message : t("agentConfig.loadFailed");
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      await api.updateAgentRunningConfig(values as AgentsRunningConfig);
      message.success(t("agentConfig.saveSuccess"));
    } catch (err) {
      if (err instanceof Error && "errorFields" in err) {
        return;
      }
      const errMsg =
        err instanceof Error ? err.message : t("agentConfig.saveFailed");
      message.error(errMsg);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    fetchConfig();
  };

  return (
    <div className={styles.page}>
      {loading && (
        <div className={styles.centerState}>
          <span className={styles.stateText}>{t("common.loading")}</span>
        </div>
      )}

      {error && !loading && (
        <div className={styles.centerState}>
          <span className={styles.stateTextError}>{error}</span>
          <Button size="small" onClick={fetchConfig} style={{ marginTop: 12 }}>
            {t("environments.retry")}
          </Button>
        </div>
      )}

      <div style={{ display: loading || error ? "none" : "block" }}>
        <div className={styles.header}>
          <p className={styles.description}>{t("agentConfig.description")}</p>
        </div>

        <Card className={styles.formCard}>
          <Form form={form} layout="vertical" className={styles.form}>
            <Form.Item
              label={t("agentConfig.maxIters")}
              name="max_iters"
              rules={[
                { required: true, message: t("agentConfig.maxItersRequired") },
                {
                  type: "number",
                  min: 1,
                  message: t("agentConfig.maxItersMin"),
                },
              ]}
              tooltip={t("agentConfig.maxItersTooltip")}
            >
              <InputNumber
                style={{ width: "100%" }}
                min={1}
                placeholder={t("agentConfig.maxItersPlaceholder")}
              />
            </Form.Item>

            <Form.Item
              label={t("agentConfig.maxInputLength")}
              name="max_input_length"
              rules={[
                {
                  required: true,
                  message: t("agentConfig.maxInputLengthRequired"),
                },
                {
                  type: "number",
                  min: 1000,
                  message: t("agentConfig.maxInputLengthMin"),
                },
              ]}
              tooltip={t("agentConfig.maxInputLengthTooltip")}
            >
              <InputNumber
                style={{ width: "100%" }}
                min={1000}
                step={1024}
                placeholder={t("agentConfig.maxInputLengthPlaceholder")}
              />
            </Form.Item>

            <Form.Item className={styles.buttonGroup}>
              <Button
                onClick={handleReset}
                disabled={saving}
                style={{ marginRight: 8 }}
              >
                {t("common.reset")}
              </Button>
              <Button type="primary" onClick={handleSave} loading={saving}>
                {t("common.save")}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    </div>
  );
}

export default AgentConfigPage;
