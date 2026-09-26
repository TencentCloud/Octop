import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Collapse,
  Form,
  Input,
  InputNumber,
  Spin,
  Switch,
  Tag,
} from "antd";
import {
  Check,
  CheckCircle2,
  FlaskConical,
  Lock,
  Save,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  ssoApi,
  type LdapConfig,
  type LdapConfigPut,
} from "../../../api/modules/sso";
import { apiErrorMessage } from "../../../utils/apiError";
import styles from "./index.module.less";

interface LdapFormValues {
  enabled: boolean;
  display_name: string;
  server_url: string;
  start_tls: boolean;
  verify_tls: boolean;
  bind_dn: string;
  bind_password?: string;
  user_base_dn: string;
  user_filter: string;
  username_attribute: string;
  email_attribute: string;
  display_name_attribute: string;
  group_attribute: string;
  admin_groups: string;
  auto_provision: boolean;
  timeout_seconds: number;
}

type TestResult = { ok: boolean; detail: string } | null;

const GUIDE_STEPS = [
  "adminSso.ldap.guideStep1",
  "adminSso.ldap.guideStep2",
  "adminSso.ldap.guideStep3",
  "adminSso.ldap.guideStep4",
  "adminSso.ldap.guideStep5",
] as const;

/** Directory-side defaults; not UI copy, so they stay code constants. */
const DEFAULT_USER_FILTER =
  "(|(uid={username})(sAMAccountName={username})(mail={username}))";
const DEFAULT_USERNAME_ATTRIBUTE = "uid";
const DEFAULT_EMAIL_ATTRIBUTE = "mail";
const DEFAULT_DISPLAY_NAME_ATTRIBUTE = "cn";
const DEFAULT_GROUP_ATTRIBUTE = "memberOf";
const DEFAULT_TIMEOUT_SECONDS = 10;

function configToFormValues(config: LdapConfig): LdapFormValues {
  return {
    enabled: config.enabled,
    display_name: config.display_name,
    server_url: config.server_url,
    start_tls: config.start_tls,
    verify_tls: config.verify_tls,
    bind_dn: config.bind_dn,
    user_base_dn: config.user_base_dn,
    user_filter: config.user_filter,
    username_attribute: config.username_attribute,
    email_attribute: config.email_attribute,
    display_name_attribute: config.display_name_attribute,
    group_attribute: config.group_attribute,
    admin_groups: config.admin_groups,
    auto_provision: config.auto_provision,
    timeout_seconds: config.timeout_seconds,
  };
}

/**
 * Directory (LDAP) sign-in. The login page keeps its plain username/password
 * form — the backend falls back to a directory bind when the local password
 * check fails — so this panel only owns the admin-side configuration.
 */
export default function LdapPanel() {
  const { t } = useTranslation();
  const [form] = Form.useForm<LdapFormValues>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [hasBindPassword, setHasBindPassword] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const hydratingRef = useRef(false);

  const enabled = Form.useWatch("enabled", form) ?? false;
  const displayName = Form.useWatch("display_name", form) ?? "";
  const serverUrl = Form.useWatch("server_url", form) ?? "";
  const userBaseDn = Form.useWatch("user_base_dn", form) ?? "";
  const userFilter = Form.useWatch("user_filter", form) ?? "";

  const applyConfig = useCallback(
    (config: LdapConfig) => {
      hydratingRef.current = true;
      form.setFieldsValue(configToFormValues(config));
      form.setFieldValue("bind_password", undefined);
      setHasBindPassword(config.has_bind_password);
      setDirty(false);
      setTestResult(null);
      queueMicrotask(() => {
        hydratingRef.current = false;
      });
    },
    [form],
  );

  // Also the retry path: the Discard button re-runs it after a failed load.
  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      applyConfig(await ssoApi.getLdapConfig());
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.ldap.loadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [applyConfig, t]);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const saveConfig = async (values: LdapFormValues) => {
    setSaving(true);
    try {
      const body: LdapConfigPut = {
        enabled: values.enabled,
        display_name: values.display_name.trim(),
        server_url: values.server_url.trim(),
        start_tls: values.start_tls,
        verify_tls: values.verify_tls,
        bind_dn: values.bind_dn.trim(),
        user_base_dn: values.user_base_dn.trim(),
        user_filter: values.user_filter.trim(),
        username_attribute: values.username_attribute.trim(),
        email_attribute: values.email_attribute.trim(),
        display_name_attribute: values.display_name_attribute.trim(),
        group_attribute: values.group_attribute.trim(),
        admin_groups: values.admin_groups.trim(),
        auto_provision: values.auto_provision,
        timeout_seconds: values.timeout_seconds,
      };
      // Write-only: an untouched field must never clobber the stored secret.
      const bindPassword = values.bind_password?.trim();
      if (bindPassword) body.bind_password = bindPassword;
      applyConfig(await ssoApi.putLdapConfig(body));
      message.success(t("adminSso.ldap.saved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.ldap.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const toggleEnabled = async (next: boolean) => {
    const previous = !next;
    const name = displayName.trim() || t("adminSso.ldap.kind");
    setToggling(true);
    try {
      await ssoApi.putLdapConfig({ enabled: next });
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
      message.error(apiErrorMessage(error, t("adminSso.ldap.saveFailed"), t));
    } finally {
      setToggling(false);
    }
  };

  const testConnection = async () => {
    if (dirty) {
      message.warning(t("adminSso.ldap.testNeedsSave"));
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const result = await ssoApi.testLdapConfig();
      const detail =
        result.detail ||
        (result.ok
          ? t("adminSso.ldap.testSuccess")
          : t("adminSso.ldap.testFailed"));
      setTestResult({ ok: result.ok, detail });
      if (result.ok) message.success(detail);
      else message.error(detail);
    } catch (error) {
      const detail = apiErrorMessage(error, t("adminSso.ldap.testFailed"), t);
      setTestResult({ ok: false, detail });
      message.error(detail);
    } finally {
      setTesting(false);
    }
  };

  const previewName = displayName.trim() || t("adminSso.ldap.kind");

  const guideStep = (() => {
    if (!serverUrl.trim() || !userBaseDn.trim() || !userFilter.trim()) return 0;
    if (dirty) return 2;
    if (!testResult?.ok) return 3;
    if (!enabled) return 4;
    return 5;
  })();

  return (
    <div className={styles.ssoProviders}>
      <Spin spinning={loading}>
        <Form<LdapFormValues>
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
            start_tls: false,
            verify_tls: true,
            auto_provision: true,
            timeout_seconds: DEFAULT_TIMEOUT_SECONDS,
            user_filter: DEFAULT_USER_FILTER,
            username_attribute: DEFAULT_USERNAME_ATTRIBUTE,
            email_attribute: DEFAULT_EMAIL_ATTRIBUTE,
            display_name_attribute: DEFAULT_DISPLAY_NAME_ATTRIBUTE,
            group_attribute: DEFAULT_GROUP_ATTRIBUTE,
          }}
          className={styles.ssoForm}
        >
          <div className={styles.ssoStandalone}>
            <div className={styles.ssoStandaloneToolbar}>
              <div className={styles.ssoStandaloneMeta}>
                <span className={styles.ssoKindBadge}>
                  {t("adminSso.ldap.kind")}
                </span>
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
              </div>
              <Form.Item
                name="enabled"
                valuePropName="checked"
                className={styles.ssoEnableSwitch}
              >
                <Switch
                  aria-label={t("adminSso.ldap.enableLabel")}
                  loading={toggling}
                  disabled={loading || saving || toggling}
                  onChange={(checked) => void toggleEnabled(checked)}
                />
              </Form.Item>
            </div>

            <div className={styles.ssoLayout}>
              <aside className={styles.ssoAside}>
                <div className={styles.ssoGuide}>
                  <div className={styles.ssoAsideTitle}>
                    {t("adminSso.guideTitle")}
                  </div>
                  <ol className={styles.ssoGuideList}>
                    {GUIDE_STEPS.map((key, index) => {
                      const done = guideStep > index;
                      const current = guideStep === index;
                      return (
                        <li
                          key={key}
                          className={[
                            styles.ssoGuideItem,
                            done ? styles.ssoGuideDone : "",
                            current ? styles.ssoGuideCurrent : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                        >
                          <span className={styles.ssoGuideIndex} aria-hidden>
                            {done ? <Check size={12} /> : index + 1}
                          </span>
                          <span>{t(key)}</span>
                        </li>
                      );
                    })}
                  </ol>
                </div>

                <div className={styles.ssoAsideCard}>
                  <div className={styles.ssoAsideTitle}>
                    {t("adminSso.loginPreview")}
                  </div>
                  <div
                    className={[
                      styles.ssoPreviewBtn,
                      enabled ? "" : styles.ssoPreviewBtnMuted,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {t("login.ldapHint", { name: previewName })}
                  </div>
                  {!enabled && (
                    <p className={styles.ssoPreviewHint}>
                      {t("adminSso.loginPreviewDisabled")}
                    </p>
                  )}
                </div>

                {testResult && (
                  <Alert
                    className={styles.ssoAlert}
                    type={testResult.ok ? "success" : "error"}
                    showIcon
                    icon={
                      testResult.ok ? (
                        <CheckCircle2 size={16} />
                      ) : (
                        <XCircle size={16} />
                      )
                    }
                    message={
                      testResult.ok
                        ? t("adminSso.ldap.testSuccess")
                        : t("adminSso.ldap.testFailed")
                    }
                    description={testResult.detail}
                    closable
                    onClose={() => setTestResult(null)}
                  />
                )}
              </aside>

              <div>
                <section className={styles.ssoSection}>
                  <div className={styles.ssoSectionHeader}>
                    <h4 className={styles.ssoSectionTitle}>
                      {t("adminSso.ldap.sectionServer")}
                    </h4>
                    <p className={styles.ssoSectionHint}>
                      {t("adminSso.ldap.sectionServerHint")}
                    </p>
                  </div>

                  <Form.Item
                    name="display_name"
                    label={t("adminSso.ldap.displayName")}
                    rules={[
                      {
                        required: true,
                        message: t("adminSso.ldap.displayNameRequired"),
                      },
                    ]}
                  >
                    <Input
                      placeholder={t("adminSso.ldap.displayNamePlaceholder")}
                    />
                  </Form.Item>

                  <Form.Item
                    name="server_url"
                    label={t("adminSso.ldap.serverUrl")}
                    extra={t("adminSso.ldap.serverUrlHint")}
                    rules={[
                      {
                        required: true,
                        message: t("adminSso.ldap.serverUrlRequired"),
                      },
                      {
                        validator: async (_, value: string | undefined) => {
                          const raw = (value ?? "").trim();
                          if (!raw) return;
                          if (!/^ldaps?:\/\/[^\s/]+/i.test(raw)) {
                            throw new Error(
                              t("adminSso.ldap.serverUrlInvalid"),
                            );
                          }
                        },
                      },
                    ]}
                  >
                    <Input
                      placeholder={t("adminSso.ldap.serverUrlPlaceholder")}
                      autoComplete="off"
                    />
                  </Form.Item>

                  <div className={styles.ssoFieldGrid}>
                    <Form.Item
                      name="start_tls"
                      label={t("adminSso.ldap.startTls")}
                      extra={t("adminSso.ldap.startTlsHint")}
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item
                      name="verify_tls"
                      label={t("adminSso.ldap.verifyTls")}
                      extra={t("adminSso.ldap.verifyTlsHint")}
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </div>
                </section>

                <section className={styles.ssoSection}>
                  <div className={styles.ssoSectionHeader}>
                    <h4 className={styles.ssoSectionTitle}>
                      {t("adminSso.ldap.sectionBind")}
                    </h4>
                    <p className={styles.ssoSectionHint}>
                      {t("adminSso.ldap.sectionBindHint")}
                    </p>
                  </div>

                  <Form.Item
                    name="bind_dn"
                    label={t("adminSso.ldap.bindDn")}
                    extra={t("adminSso.ldap.bindDnHint")}
                  >
                    <Input
                      placeholder={t("adminSso.ldap.bindDnPlaceholder")}
                      autoComplete="off"
                    />
                  </Form.Item>

                  <Form.Item
                    name="bind_password"
                    label={
                      <span className={styles.ssoSecretLabel}>
                        {t("adminSso.ldap.bindPassword")}
                        {hasBindPassword && (
                          <Tag className={styles.ssoSecretTag}>
                            <Lock size={11} />
                            {t("adminSso.ldap.bindPasswordConfiguredTag")}
                          </Tag>
                        )}
                      </span>
                    }
                    extra={
                      hasBindPassword
                        ? t("adminSso.ldap.bindPasswordConfigured")
                        : t("adminSso.ldap.bindPasswordHint")
                    }
                  >
                    <Input.Password
                      autoComplete="new-password"
                      placeholder={
                        hasBindPassword
                          ? t("adminSso.ldap.bindPasswordPlaceholder")
                          : undefined
                      }
                    />
                  </Form.Item>
                </section>

                <section className={styles.ssoSection}>
                  <div className={styles.ssoSectionHeader}>
                    <h4 className={styles.ssoSectionTitle}>
                      {t("adminSso.ldap.sectionSearch")}
                    </h4>
                    <p className={styles.ssoSectionHint}>
                      {t("adminSso.ldap.sectionSearchHint")}
                    </p>
                  </div>

                  <Form.Item
                    name="user_base_dn"
                    label={t("adminSso.ldap.userBaseDn")}
                    rules={[
                      {
                        required: true,
                        message: t("adminSso.ldap.userBaseDnRequired"),
                      },
                    ]}
                  >
                    <Input
                      placeholder={t("adminSso.ldap.userBaseDnPlaceholder")}
                      autoComplete="off"
                    />
                  </Form.Item>

                  <Form.Item
                    name="user_filter"
                    label={t("adminSso.ldap.userFilter")}
                    extra={t("adminSso.ldap.userFilterHint")}
                    rules={[
                      {
                        required: true,
                        message: t("adminSso.ldap.userFilterRequired"),
                      },
                      {
                        validator: async (_, value: string | undefined) => {
                          const raw = (value ?? "").trim();
                          if (raw && !raw.includes("{username}")) {
                            throw new Error(
                              t("adminSso.ldap.userFilterPlaceholderRequired"),
                            );
                          }
                        },
                      },
                    ]}
                  >
                    <Input
                      placeholder={t("adminSso.ldap.userFilterPlaceholder")}
                      autoComplete="off"
                    />
                  </Form.Item>
                </section>

                <section className={styles.ssoSection}>
                  <div className={styles.ssoSectionHeader}>
                    <h4 className={styles.ssoSectionTitle}>
                      {t("adminSso.ldap.sectionAttributes")}
                    </h4>
                    <p className={styles.ssoSectionHint}>
                      {t("adminSso.ldap.sectionAttributesHint")}
                    </p>
                  </div>

                  <div className={styles.ssoFieldGrid}>
                    <Form.Item
                      name="username_attribute"
                      label={t("adminSso.ldap.usernameAttribute")}
                      rules={[
                        {
                          required: true,
                          message: t("adminSso.ldap.usernameAttributeRequired"),
                        },
                      ]}
                    >
                      <Input autoComplete="off" />
                    </Form.Item>
                    <Form.Item
                      name="email_attribute"
                      label={t("adminSso.ldap.emailAttribute")}
                    >
                      <Input autoComplete="off" />
                    </Form.Item>
                    <Form.Item
                      name="display_name_attribute"
                      label={t("adminSso.ldap.displayNameAttribute")}
                    >
                      <Input autoComplete="off" />
                    </Form.Item>
                    <Form.Item
                      name="group_attribute"
                      label={t("adminSso.ldap.groupAttribute")}
                    >
                      <Input autoComplete="off" />
                    </Form.Item>
                  </div>
                </section>

                <section className={styles.ssoSection}>
                  <div className={styles.ssoSectionHeader}>
                    <h4 className={styles.ssoSectionTitle}>
                      {t("adminSso.ldap.sectionAccess")}
                    </h4>
                    <p className={styles.ssoSectionHint}>
                      {t("adminSso.ldap.sectionAccessHint")}
                    </p>
                  </div>

                  <Form.Item
                    name="admin_groups"
                    label={t("adminSso.ldap.adminGroups")}
                    extra={t("adminSso.ldap.adminGroupsHint")}
                  >
                    <Input
                      placeholder={t("adminSso.ldap.adminGroupsPlaceholder")}
                      autoComplete="off"
                    />
                  </Form.Item>

                  <Form.Item
                    name="auto_provision"
                    label={t("adminSso.ldap.autoProvision")}
                    extra={t("adminSso.ldap.autoProvisionHint")}
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                </section>

                <Collapse
                  ghost
                  className={styles.ssoAdvanced}
                  items={[
                    {
                      key: "advanced",
                      label: t("adminSso.sectionAdvanced"),
                      children: (
                        <Form.Item
                          name="timeout_seconds"
                          label={t("adminSso.ldap.timeout")}
                          extra={t("adminSso.ldap.timeoutHint")}
                          rules={[
                            {
                              required: true,
                              message: t("adminSso.ldap.timeoutRequired"),
                            },
                          ]}
                        >
                          <InputNumber
                            min={1}
                            max={60}
                            style={{ width: "100%" }}
                          />
                        </Form.Item>
                      ),
                    },
                  ]}
                />

                <div className={styles.ssoFooter}>
                  <div className={styles.ssoFooterActions}>
                    <Button
                      type="primary"
                      htmlType="submit"
                      icon={<Save size={15} />}
                      loading={saving}
                    >
                      {t("adminSso.ldap.save")}
                    </Button>
                    <Button
                      icon={<FlaskConical size={15} />}
                      loading={testing}
                      disabled={dirty}
                      onClick={() => void testConnection()}
                    >
                      {t("adminSso.ldap.testConnection")}
                    </Button>
                    {dirty && (
                      <Button
                        type="link"
                        onClick={() => void loadConfig()}
                        disabled={saving || loading}
                      >
                        {t("adminSso.ldap.discard")}
                      </Button>
                    )}
                  </div>
                  <div className={styles.ssoFooterMeta}>
                    {dirty ? (
                      <span className={styles.ssoDirtyHint}>
                        {t("adminSso.ldap.unsavedChanges")}
                      </span>
                    ) : (
                      <span className={styles.ssoTestHint}>
                        {t("adminSso.ldap.testHint")}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Form>
      </Spin>
    </div>
  );
}
