import { useEffect, useState } from "react";
import { Form, Button, Card } from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import { AgentAdvancedConfigFields } from "../../../components/AgentAdvancedConfigFields";
import { useAgent } from "../../../context/AgentContext";
import {
  buildAgentRuntimeRequest,
  readAgentRuntimeFormValues,
} from "../../../utils/agentRuntimeConfig";
import styles from "./index.module.less";

function AgentConfigPage() {
  const { t } = useTranslation();
  const { activeAgent, activeAgentId } = useAgent();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeAgentId) {
      setLoading(false);
      setError(t("agentConfig.noActiveAgent"));
      return;
    }
    setLoading(true);
    setError(null);
    form.setFieldsValue(readAgentRuntimeFormValues(activeAgent ?? {}));
    setLoading(false);
  }, [activeAgent, activeAgentId, form, t]);

  const handleSave = async () => {
    if (!activeAgentId) return;
    try {
      const values = await form.validateFields();
      setSaving(true);
      await request(`/agents/${activeAgentId}`, {
        method: "PATCH",
        body: JSON.stringify({
          ...buildAgentRuntimeRequest(values, { clearMissing: true }),
        }),
      });
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
    form.setFieldsValue(readAgentRuntimeFormValues(activeAgent ?? {}));
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
        </div>
      )}

      <div style={{ display: loading || error ? "none" : "block" }}>
        <div className={styles.header}>
          <p className={styles.description}>{t("agentConfig.description")}</p>
        </div>

        <Card className={styles.formCard}>
          <Form form={form} layout="vertical" className={styles.form}>
            <AgentAdvancedConfigFields requireLimits />

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
