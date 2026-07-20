import { useState } from "react";
import { Form, Input, Button, Alert, Typography, Space } from "antd";
import { User, Lock, IdCard } from "lucide-react";
import { useTranslation } from "react-i18next";

import { wizardApi, wizardSession } from "../wizardClient";
import { setAuthToken } from "../../../api/request";

const { Text } = Typography;

interface FormValues {
  username: string;
  display_name?: string;
  password: string;
  confirm: string;
}

interface Props {
  /** When returning from a later step, admin was already created in this session. */
  createdCreds?: { username: string; password: string } | null;
  onBack?: () => void;
  /** Called with the username + plaintext password held in memory only. */
  onCreated: (creds: { username: string; password: string }) => void;
}

export default function AdminStep({ createdCreds, onBack, onCreated }: Props) {
  const { t, i18n } = useTranslation();
  const [form] = Form.useForm<FormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFinish = async (values: FormValues) => {
    setError(null);
    if (values.password !== values.confirm) {
      setError(t("wizard.admin.passwordMismatch"));
      return;
    }
    const wizardToken = wizardSession.loadToken();
    if (!wizardToken) {
      setError(t("wizard.sessionExpired"));
      return;
    }
    setSubmitting(true);
    try {
      const locale = i18n.language?.startsWith("zh") ? "zh" : "en";
      const created = await wizardApi.createAdmin(
        {
          username: values.username,
          display_name: values.display_name?.trim() || null,
          password: values.password,
          locale,
        },
        wizardToken,
      );
      wizardSession.saveSetupJwt(created.access_token);
      // So mid-wizard locale / preferences API calls can authenticate.
      setAuthToken(created.access_token);
      onCreated({ username: values.username, password: values.password });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (createdCreds) {
    return (
      <>
        <div style={{ marginBottom: 20 }}>
          <div
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "var(--fn-text-primary)",
              marginBottom: 4,
            }}
          >
            {t("wizard.stepAdmin")}
          </div>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {t("wizard.admin.intro")}
          </Text>
        </div>

        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("wizard.admin.alreadyCreated", {
            username: createdCreds.username,
          })}
        />

        <Space style={{ width: "100%", justifyContent: "flex-end" }}>
          <Button type="primary" onClick={() => onCreated(createdCreds)}>
            {t("wizard.admin.continue")}
          </Button>
        </Space>
      </>
    );
  }

  return (
    <>
      <div style={{ marginBottom: 20 }}>
        <div
          style={{
            fontSize: 16,
            fontWeight: 600,
            color: "var(--fn-text-primary)",
            marginBottom: 4,
          }}
        >
          {t("wizard.stepAdmin")}
        </div>
        <Text type="secondary" style={{ fontSize: 13 }}>
          {t("wizard.admin.intro")}
        </Text>
      </div>
      <Form<FormValues>
        form={form}
        layout="vertical"
        onFinish={onFinish}
        requiredMark={false}
      >
        <Form.Item
          label={t("wizard.admin.username")}
          name="username"
          rules={[
            { required: true, message: t("wizard.admin.username") as string },
            {
              pattern: /^[a-zA-Z0-9_-]{1,64}$/,
              message: t("wizard.admin.usernameRule") as string,
            },
          ]}
        >
          <Input prefix={<User size={16} />} autoFocus />
        </Form.Item>

        <Form.Item label={t("wizard.admin.displayName")} name="display_name">
          <Input prefix={<IdCard size={16} />} />
        </Form.Item>

        <Form.Item
          label={t("wizard.admin.password")}
          name="password"
          rules={[
            { required: true, message: t("wizard.admin.password") as string },
          ]}
        >
          <Input.Password
            prefix={<Lock size={16} />}
            autoComplete="new-password"
          />
        </Form.Item>

        <Form.Item
          label={t("wizard.admin.confirm")}
          name="confirm"
          dependencies={["password"]}
          rules={[
            { required: true, message: t("wizard.admin.confirm") as string },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("password") === value) {
                  return Promise.resolve();
                }
                return Promise.reject(
                  new Error(t("wizard.admin.passwordMismatch") as string),
                );
              },
            }),
          ]}
        >
          <Input.Password
            prefix={<Lock size={16} />}
            autoComplete="new-password"
          />
        </Form.Item>

        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            style={{ marginBottom: 12 }}
          />
        )}

        <Space style={{ width: "100%", justifyContent: "space-between" }}>
          {onBack ? <Button onClick={onBack}>{t("wizard.back")}</Button> : null}
          <Button
            type="primary"
            htmlType="submit"
            size="large"
            loading={submitting}
          >
            {t("wizard.admin.submit")}
          </Button>
        </Space>
      </Form>
    </>
  );
}
