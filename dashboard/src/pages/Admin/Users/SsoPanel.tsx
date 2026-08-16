import { useCallback, useEffect, useState } from "react";
import { Button, Form, Input, Space, Spin, Switch, Typography } from "antd";
import { Copy, FlaskConical, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  ssoApi,
  type OidcConfig,
  type OidcConfigPut,
} from "../../../api/modules/sso";
import { apiErrorMessage } from "../../../utils/apiError";

interface SsoFormValues {
  enabled: boolean;
  display_name: string;
  issuer: string;
  client_id: string;
  client_secret?: string;
  scopes: string;
  dashboard_origin?: string;
}

function configToFormValues(config: OidcConfig): SsoFormValues {
  return {
    enabled: config.enabled,
    display_name: config.display_name,
    issuer: config.issuer,
    client_id: config.client_id,
    scopes: config.scopes,
    dashboard_origin: config.dashboard_origin ?? "",
  };
}

export default function SsoPanel() {
  const { t } = useTranslation();
  const [form] = Form.useForm<SsoFormValues>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [redirectUri, setRedirectUri] = useState("");
  const [hasClientSecret, setHasClientSecret] = useState(false);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const config = await ssoApi.getOidcConfig();
      form.setFieldsValue(configToFormValues(config));
      setRedirectUri(config.redirect_uri ?? "");
      setHasClientSecret(config.has_client_secret);
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.loadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [form, t]);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const saveConfig = async (values: SsoFormValues) => {
    setSaving(true);
    try {
      const body: OidcConfigPut = {
        ...values,
        client_secret: values.client_secret?.trim() || undefined,
        dashboard_origin: values.dashboard_origin?.trim() || null,
      };
      const saved = await ssoApi.putOidcConfig(body);
      form.setFieldsValue(configToFormValues(saved));
      form.setFieldValue("client_secret", undefined);
      setHasClientSecret(saved.has_client_secret);
      if (saved.redirect_uri) {
        setRedirectUri(saved.redirect_uri);
      }
      message.success(t("adminSso.saved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    try {
      const result = await ssoApi.testOidcConfig();
      if (result.ok) {
        message.success(result.detail || t("adminSso.testSuccess"));
      } else {
        message.error(result.detail || t("adminSso.testFailed"));
      }
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.testFailed"), t));
    } finally {
      setTesting(false);
    }
  };

  const copyRedirectUri = async () => {
    try {
      await navigator.clipboard.writeText(redirectUri);
      message.success(t("adminSso.copySuccess"));
    } catch {
      message.error(t("adminSso.copyFailed"));
    }
  };

  return (
    <Spin spinning={loading}>
      <Form<SsoFormValues>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => void saveConfig(values)}
        style={{ maxWidth: 680 }}
        initialValues={{ enabled: false, scopes: "openid profile email" }}
      >
        <Form.Item
          name="enabled"
          label={t("adminSso.enabled")}
          valuePropName="checked"
          extra={t("adminSso.enabledHint")}
        >
          <Switch />
        </Form.Item>
        <Form.Item
          name="display_name"
          label={t("adminSso.displayName")}
          rules={[
            { required: true, message: t("adminSso.displayNameRequired") },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name="issuer"
          label={t("adminSso.issuer")}
          extra={t("adminSso.issuerHint")}
          rules={[
            {
              required: true,
              type: "url",
              message: t("adminSso.issuerRequired"),
            },
          ]}
        >
          <Input placeholder="https://identity.example.com" />
        </Form.Item>
        <Form.Item
          name="client_id"
          label={t("adminSso.clientId")}
          rules={[{ required: true, message: t("adminSso.clientIdRequired") }]}
        >
          <Input autoComplete="off" />
        </Form.Item>
        <Form.Item
          name="client_secret"
          label={t("adminSso.clientSecret")}
          extra={
            hasClientSecret
              ? t("adminSso.clientSecretConfigured")
              : t("adminSso.clientSecretHint")
          }
        >
          <Input.Password
            autoComplete="new-password"
            placeholder={
              hasClientSecret
                ? t("adminSso.clientSecretPlaceholder")
                : undefined
            }
          />
        </Form.Item>
        <Form.Item
          name="scopes"
          label={t("adminSso.scopes")}
          rules={[{ required: true, message: t("adminSso.scopesRequired") }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name="dashboard_origin"
          label={t("adminSso.dashboardOrigin")}
          extra={t("adminSso.dashboardOriginHint")}
          rules={[
            { type: "url", message: t("adminSso.dashboardOriginInvalid") },
          ]}
        >
          <Input placeholder="https://octop.example.com" />
        </Form.Item>
        <Form.Item
          label={t("adminSso.redirectUri")}
          extra={t("adminSso.redirectUriHint")}
        >
          <Space.Compact style={{ width: "100%" }}>
            <Input readOnly value={redirectUri} />
            <Button
              icon={<Copy size={15} />}
              onClick={() => void copyRedirectUri()}
              aria-label={t("adminSso.copyRedirectUri")}
            >
              {t("adminSso.copy")}
            </Button>
          </Space.Compact>
        </Form.Item>
        <Space>
          <Button
            type="primary"
            htmlType="submit"
            icon={<Save size={15} />}
            loading={saving}
          >
            {t("adminSso.save")}
          </Button>
          <Button
            icon={<FlaskConical size={15} />}
            loading={testing}
            onClick={() => void testConnection()}
          >
            {t("adminSso.testConnection")}
          </Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
          {t("adminSso.testHint")}
        </Typography.Paragraph>
      </Form>
    </Spin>
  );
}
