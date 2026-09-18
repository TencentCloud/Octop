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
  /** Full-page tab: no Collapse wrapper. */
  standalone?: boolean;
}

/** Shared admin card for one App ID / Secret OAuth provider. */
export default function OauthProviderCard({
  provider,
  standalone = false,
}: OauthProviderCardProps) {
  const { t } = useTranslation();

  if (!provider.available) {
    if (standalone) {
      return (
        <div className={styles.ssoStandalone}>
          <p className={styles.ssoComingSoonBody}>
            {t("adminSso.oauthComingSoonHint", {
              name: t(provider.defaultNameKey),
            })}
          </p>
        </div>
      );
    }
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

  return <OauthProviderCardLive provider={provider} standalone={standalone} />;
}

function OauthProviderCardLive({
  provider,
  standalone,
}: OauthProviderCardProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<OauthFormValues>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean } | null>(null);
  const [toggling, setToggling] = useState(false);
  const [redirectUri, setRedirectUri] = useState("");
  const [hasClientSecret, setHasClientSecret] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedDomain, setCopiedDomain] = useState(false);
  const hydratingRef = useRef(false);
  const enabled = Form.useWatch("enabled", form) ?? false;
  const displayName = Form.useWatch("display_name", form) ?? "";
  const clientId = Form.useWatch("client_id", form) ?? "";
  const agentId = Form.useWatch("agent_id", form) ?? "";

  const applyConfig = useCallback(
    (config: OauthAppConfig) => {
      hydratingRef.current = true;
      form.setFieldsValue({
        enabled: config.enabled,
        display_name: config.display_name.trim() || t(provider.defaultNameKey),
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
      setTestResult(null);
      queueMicrotask(() => {
        hydratingRef.current = false;
      });
    },
    [form, provider.defaultNameKey, t],
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

  const toggleEnabled = async (next: boolean) => {
    const previous = !next;
    const name = displayName.trim() || t(provider.defaultNameKey);
    setToggling(true);
    try {
      await ssoApi.putOauthProvider(provider.kind, { enabled: next });
      message.success(
        next
          ? t("adminSso.statusEnabled", { name })
          : t("adminSso.statusDisabled"),
      );
    } catch (error) {
      hydratingRef.current = true;
      form.setFieldsValue({ enabled: previous });
      queueMicrotask(() => {
        hydratingRef.current = false;
      });
      message.error(apiErrorMessage(error, t("adminSso.saveFailed"), t));
    } finally {
      setToggling(false);
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
      setTestResult({ ok: result.ok });
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
      setTestResult({ ok: false });
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

  const callbackDomain = (() => {
    if (!provider.showCallbackDomain || !redirectUri) return "";
    try {
      return new URL(redirectUri).hostname;
    } catch {
      return "";
    }
  })();

  const copyCallbackDomain = async () => {
    if (!callbackDomain) return;
    const ok = await copyText(callbackDomain);
    if (ok) {
      message.success(t("adminSso.copyDomainSuccess"));
      setCopiedDomain(true);
      window.setTimeout(() => setCopiedDomain(false), 2000);
    } else {
      message.error(t("adminSso.copyFailed"));
    }
  };

  const previewName = displayName.trim() || t(provider.defaultNameKey);

  const guideStep = (() => {
    const credentialsReady =
      Boolean(clientId.trim()) &&
      (!provider.hasAgentId || Boolean(String(agentId).trim()));
    if (!credentialsReady) return 0;
    if (!redirectUri) return 1;
    if (dirty) return 2;
    if (!testResult?.ok) return 3;
    if (!enabled) return 4;
    return 5;
  })();

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
        onValuesChange={(changed) => {
          if (hydratingRef.current) return;
          const keys = Object.keys(changed);
          if (keys.length === 1 && keys[0] === "enabled") return;
          setDirty(true);
          setTestResult(null);
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
          standalone={standalone}
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
              <Switch
                aria-label={t(provider.enabledAriaKey)}
                loading={toggling}
                disabled={loading || saving || toggling}
                onChange={(checked) => void toggleEnabled(checked)}
              />
            </Form.Item>
          }
          redirectUri={redirectUri}
          redirectHint={t(
            provider.redirectHintKey ?? "adminSso.oauthRedirectHint",
            { name: t(provider.defaultNameKey) },
          )}
          redirectDocs={t(
            provider.redirectDocsKey ?? "adminSso.oauthRedirectDocs",
          )}
          callbackDomain={callbackDomain || undefined}
          callbackDomainHint={
            provider.showCallbackDomain
              ? t("adminSso.wecomCallbackDomainHint")
              : undefined
          }
          copied={copied}
          copiedDomain={copiedDomain}
          onCopyRedirect={() => void copyRedirectUri()}
          onCopyDomain={
            provider.showCallbackDomain
              ? () => void copyCallbackDomain()
              : undefined
          }
          guideStep={guideStep}
          enabled={enabled}
          previewName={previewName}
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
