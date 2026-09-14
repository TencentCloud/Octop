import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button, Form, Input, Select, Spin, Switch, Tag } from "antd";
import { FlaskConical, Lock, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  ssoApi,
  type OauthAppConfig,
  type OauthAppConfigPut,
} from "../../../api/modules/sso";
import { apiErrorMessage } from "../../../utils/apiError";
import { copyText } from "../../../utils/copyText";
import SsoAppProviderShell from "./SsoAppProviderShell";
import SsoProviderCard from "./SsoProviderCard";
import type { OauthProviderDef } from "./oauthProviders";
import styles from "./index.module.less";

interface OauthFormValues {
  enabled: boolean;
  display_name: string;
  client_id: string;
  client_secret?: string;
  region?: "feishu" | "lark";
  agent_id?: string;
}

interface OauthProviderCardProps {
  provider: OauthProviderDef;
}

/** Shared admin card for one App ID / Secret OAuth provider (Feishu today). */
export default function OauthProviderCard({
  provider,
}: OauthProviderCardProps) {
  const { t } = useTranslation();

  if (!provider.available) {
    return (
      <SsoProviderCard
        kind={t("adminSso.oauthKind")}
        title={t(provider.titleKey)}
        description={t(provider.descKey)}
        extra={
          <Tag className={styles.ssoStatusTagOff}>
            <span className={styles.ssoStatusDotOff} />
            {t("adminSso.oauthComingSoon")}
          </Tag>
        }
      >
        <p className={styles.ssoComingSoonBody}>
          {t("adminSso.oauthComingSoonHint", {
            name: t(provider.defaultNameKey),
          })}
        </p>
      </SsoProviderCard>
    );
  }

  return <OauthProviderCardLive provider={provider} />;
}

function OauthProviderCardLive({ provider }: OauthProviderCardProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<OauthFormValues>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [redirectUri, setRedirectUri] = useState("");
  const [hasClientSecret, setHasClientSecret] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [copied, setCopied] = useState(false);
  const hydratingRef = useRef(false);
  const enabled = Form.useWatch("enabled", form) ?? false;
  const displayName = Form.useWatch("display_name", form) ?? "";

  const applyConfig = useCallback(
    (config: OauthAppConfig) => {
      hydratingRef.current = true;
      form.setFieldsValue({
        enabled: config.enabled,
        display_name: config.display_name,
        client_id: config.client_id,
        client_secret: undefined,
        region: config.extra?.region === "lark" ? "lark" : "feishu",
        agent_id:
          typeof config.extra?.agent_id === "string"
            ? config.extra.agent_id
            : "",
      });
      setRedirectUri(config.redirect_uri ?? "");
      setHasClientSecret(config.has_client_secret);
      setDirty(false);
      queueMicrotask(() => {
        hydratingRef.current = false;
      });
    },
    [form],
  );

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      applyConfig(await ssoApi.getOauthProvider(provider.kind));
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.loadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [applyConfig, provider.kind, t]);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const saveConfig = async (values: OauthFormValues) => {
    setSaving(true);
    try {
      const body: OauthAppConfigPut = {
        enabled: values.enabled,
        display_name: values.display_name.trim(),
        client_id: values.client_id.trim(),
        client_secret: values.client_secret?.trim() || undefined,
      };
      if (provider.hasRegion) {
        body.extra = { region: values.region === "lark" ? "lark" : "feishu" };
      }
      if (provider.hasAgentId) {
        body.extra = {
          ...body.extra,
          agent_id: values.agent_id?.trim() || "",
        };
      }
      applyConfig(await ssoApi.putOauthProvider(provider.kind, body));
      message.success(
        t("adminSso.oauthSaved", { name: t(provider.defaultNameKey) }),
      );
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    if (dirty) {
      message.warning(t("adminSso.testNeedsSave"));
      return;
    }
    setTesting(true);
    try {
      const result = await ssoApi.testOauthProvider(provider.kind);
      const detail =
        result.detail ||
        (result.ok
          ? t("adminSso.oauthTestSuccess", {
              name: t(provider.defaultNameKey),
            })
          : t("adminSso.oauthTestFailed", {
              name: t(provider.defaultNameKey),
            }));
      if (result.ok) message.success(detail);
      else message.error(detail);
    } catch (error) {
      message.error(
        apiErrorMessage(
          error,
          t("adminSso.oauthTestFailed", { name: t(provider.defaultNameKey) }),
          t,
        ),
      );
    } finally {
      setTesting(false);
    }
  };

  const copyRedirectUri = async () => {
    if (!redirectUri) return;
    const ok = await copyText(redirectUri);
    if (ok) {
      message.success(t("adminSso.copySuccess"));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } else {
      message.error(t("adminSso.copyFailed"));
    }
  };

  const previewName = displayName.trim() || t(provider.defaultNameKey);

  const extraFields: ReactNode = (
    <>
      {provider.hasRegion ? (
        <Form.Item name="region" label={t("adminSso.feishuRegion")}>
          <Select
            options={[
              {
                value: "feishu",
                label: t("adminSso.feishuRegionFeishu"),
              },
              { value: "lark", label: t("adminSso.feishuRegionLark") },
            ]}
          />
        </Form.Item>
      ) : null}
      {provider.hasAgentId ? (
        <Form.Item
          name="agent_id"
          label={t("adminSso.wecomAgentId")}
          rules={[
            { required: true, message: t("adminSso.wecomAgentIdRequired") },
          ]}
        >
          <Input autoComplete="off" />
        </Form.Item>
      ) : null}
    </>
  );

  return (
    <Spin spinning={loading}>
      <Form<OauthFormValues>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => void saveConfig(values)}
        onValuesChange={() => {
          if (hydratingRef.current) return;
          setDirty(true);
        }}
        initialValues={{
          enabled: false,
          region: provider.hasRegion ? "feishu" : undefined,
        }}
        className={styles.ssoForm}
      >
        <SsoAppProviderShell
          kind={t("adminSso.oauthKind")}
          title={t(provider.titleKey)}
          description={t(provider.descKey)}
          statusLabel={
            <Tag
              className={
                enabled ? styles.ssoStatusTagOn : styles.ssoStatusTagOff
              }
            >
              <span
                className={
                  enabled ? styles.ssoStatusDotOn : styles.ssoStatusDotOff
                }
              />
              {enabled
                ? t("adminSso.statusEnabled", { name: previewName })
                : t("adminSso.statusDisabled")}
            </Tag>
          }
          enableSwitch={
            <Form.Item
              name="enabled"
              valuePropName="checked"
              className={styles.ssoEnableSwitch}
            >
              <Switch aria-label={t(provider.enabledAriaKey)} />
            </Form.Item>
          }
          redirectUri={redirectUri}
          redirectHint={t("adminSso.oauthRedirectHint", {
            name: t(provider.defaultNameKey),
          })}
          copied={copied}
          onCopyRedirect={() => void copyRedirectUri()}
        >
          <section className={styles.ssoSection}>
            <div className={styles.ssoSectionHeader}>
              <h4 className={styles.ssoSectionTitle}>
                {t("adminSso.sectionProvider")}
              </h4>
              <p className={styles.ssoSectionHint}>
                {t("adminSso.oauthSectionProviderHint")}
              </p>
            </div>
            <Form.Item
              name="display_name"
              label={t("adminSso.displayName")}
              rules={[
                {
                  required: true,
                  message: t("adminSso.displayNameRequired"),
                },
              ]}
            >
              <Input placeholder={t("adminSso.displayNamePlaceholder")} />
            </Form.Item>
          </section>

          <section className={styles.ssoSection}>
            <div className={styles.ssoSectionHeader}>
              <h4 className={styles.ssoSectionTitle}>
                {t("adminSso.oauthSectionCredentials")}
              </h4>
              <p className={styles.ssoSectionHint}>
                {t("adminSso.oauthSectionCredentialsHint")}
              </p>
            </div>
            <div className={styles.ssoFieldGrid}>
              <Form.Item
                name="client_id"
                label={t(provider.clientIdKey ?? "adminSso.oauthAppId")}
                rules={[
                  { required: true, message: t("adminSso.clientIdRequired") },
                ]}
              >
                <Input autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="client_secret"
                label={
                  <span className={styles.ssoSecretLabel}>
                    {t(provider.clientSecretKey ?? "adminSso.oauthAppSecret")}
                    {hasClientSecret && (
                      <Tag className={styles.ssoSecretTag}>
                        <Lock size={11} />
                        {t("adminSso.clientSecretConfiguredTag")}
                      </Tag>
                    )}
                  </span>
                }
                extra={
                  hasClientSecret
                    ? t("adminSso.clientSecretConfigured")
                    : t("adminSso.oauthClientSecretHint")
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
            </div>
            {extraFields}
          </section>

          <div className={styles.ssoFooter}>
            <div className={styles.ssoFooterActions}>
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
                disabled={dirty}
                onClick={() => void testConnection()}
              >
                {t("adminSso.testConnection")}
              </Button>
              {dirty && (
                <Button
                  type="link"
                  onClick={() => void loadConfig()}
                  disabled={saving || loading}
                >
                  {t("adminSso.discard")}
                </Button>
              )}
            </div>
            <div className={styles.ssoFooterMeta}>
              {dirty ? (
                <span className={styles.ssoDirtyHint}>
                  {t("adminSso.unsavedChanges")}
                </span>
              ) : (
                <span className={styles.ssoTestHint}>
                  {t("adminSso.oauthTestHint")}
                </span>
              )}
            </div>
          </div>
        </SsoAppProviderShell>
      </Form>
    </Spin>
  );
}
