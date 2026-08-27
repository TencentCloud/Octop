import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import {
  Alert,
  Button,
  Collapse,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  Check,
  CheckCircle2,
  Copy,
  FlaskConical,
  KeyRound,
  Lock,
  Save,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  ssoApi,
  type OidcConfig,
  type OidcConfigPut,
} from "../../../api/modules/sso";
import { apiErrorMessage } from "../../../utils/apiError";
import { copyText } from "../../../utils/copyText";
import { TabPanelHeader } from "../../Settings/AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

interface SsoFormValues {
  enabled: boolean;
  display_name: string;
  issuer: string;
  client_id: string;
  client_secret?: string;
  scopes: string[];
  dashboard_origin?: string;
}

type TestResult = { ok: boolean; detail: string } | null;

type IdpPresetId = "azure" | "google" | "keycloak" | "okta";

interface IdpPreset {
  id: IdpPresetId;
  labelKey: string;
  displayName: string;
  scopes: string[];
  issuerPlaceholder: string;
}

const IDP_PRESETS: IdpPreset[] = [
  {
    id: "azure",
    labelKey: "adminSso.presetAzure",
    displayName: "Microsoft",
    scopes: ["openid", "profile", "email"],
    issuerPlaceholder: "https://login.microsoftonline.com/{tenant}/v2.0",
  },
  {
    id: "google",
    labelKey: "adminSso.presetGoogle",
    displayName: "Google",
    scopes: ["openid", "profile", "email"],
    issuerPlaceholder: "https://accounts.google.com",
  },
  {
    id: "keycloak",
    labelKey: "adminSso.presetKeycloak",
    displayName: "Keycloak",
    scopes: ["openid", "profile", "email"],
    issuerPlaceholder: "https://keycloak.example.com/realms/{realm}",
  },
  {
    id: "okta",
    labelKey: "adminSso.presetOkta",
    displayName: "Okta",
    scopes: ["openid", "profile", "email"],
    issuerPlaceholder: "https://{domain}.okta.com",
  },
];

const SCOPE_OPTIONS = ["openid", "profile", "email", "offline_access"].map(
  (value) => ({ value, label: value }),
);

const GUIDE_STEPS = [
  "adminSso.guideStep1",
  "adminSso.guideStep2",
  "adminSso.guideStep3",
  "adminSso.guideStep4",
  "adminSso.guideStep5",
] as const;

function configToFormValues(config: OidcConfig): SsoFormValues {
  return {
    enabled: config.enabled,
    display_name: config.display_name,
    issuer: config.issuer,
    client_id: config.client_id,
    scopes: config.scopes
      .split(/\s+/)
      .map((s) => s.trim())
      .filter(Boolean),
    dashboard_origin: config.dashboard_origin ?? "",
  };
}

function normalizeIssuer(raw: string): string {
  return raw.trim().replace(/\/+$/, "");
}

export default function SsoPanel() {
  const { t } = useTranslation();
  const [form] = Form.useForm<SsoFormValues>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [redirectUri, setRedirectUri] = useState("");
  const [hasClientSecret, setHasClientSecret] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [copied, setCopied] = useState(false);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [issuerPlaceholder, setIssuerPlaceholder] = useState(
    "https://identity.example.com",
  );
  const [activePreset, setActivePreset] = useState<IdpPresetId | null>(null);
  const hydratingRef = useRef(false);

  const enabled = Form.useWatch("enabled", form) ?? false;
  const displayName = Form.useWatch("display_name", form) ?? "";
  const issuer = Form.useWatch("issuer", form) ?? "";
  const clientId = Form.useWatch("client_id", form) ?? "";

  const applyConfig = useCallback(
    (config: OidcConfig) => {
      hydratingRef.current = true;
      form.setFieldsValue(configToFormValues(config));
      form.setFieldValue("client_secret", undefined);
      setRedirectUri(config.redirect_uri ?? "");
      setHasClientSecret(config.has_client_secret);
      setDirty(false);
      setTestResult(null);
      setActivePreset(null);
      queueMicrotask(() => {
        hydratingRef.current = false;
      });
    },
    [form],
  );

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const config = await ssoApi.getOidcConfig();
      applyConfig(config);
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminSso.loadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [applyConfig, t]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const config = await ssoApi.getOidcConfig();
        if (cancelled) return;
        applyConfig(config);
      } catch (error) {
        if (cancelled) return;
        message.error(apiErrorMessage(error, t("adminSso.loadFailed"), t));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Mount-only load; reload goes through loadConfig().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveConfig = async (values: SsoFormValues) => {
    setSaving(true);
    try {
      const body: OidcConfigPut = {
        enabled: values.enabled,
        display_name: values.display_name.trim(),
        issuer: normalizeIssuer(values.issuer),
        client_id: values.client_id.trim(),
        client_secret: values.client_secret?.trim() || undefined,
        scopes: values.scopes.join(" "),
        dashboard_origin: values.dashboard_origin?.trim() || null,
      };
      const saved = await ssoApi.putOidcConfig(body);
      applyConfig(saved);
      message.success(t("adminSso.saved"));
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
    setTestResult(null);
    try {
      const result = await ssoApi.testOidcConfig();
      const detail =
        result.detail ||
        (result.ok ? t("adminSso.testSuccess") : t("adminSso.testFailed"));
      setTestResult({ ok: result.ok, detail });
      if (result.ok) message.success(detail);
      else message.error(detail);
    } catch (error) {
      const detail = apiErrorMessage(error, t("adminSso.testFailed"), t);
      setTestResult({ ok: false, detail });
      message.error(detail);
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

  const applyPreset = (preset: IdpPreset) => {
    form.setFieldsValue({
      display_name: preset.displayName,
      scopes: preset.scopes,
    });
    setIssuerPlaceholder(preset.issuerPlaceholder);
    setActivePreset(preset.id);
    setDirty(true);
    setTestResult(null);
  };

  const guideStep = (() => {
    if (!issuer.trim() || !clientId.trim()) return 0;
    if (!redirectUri) return 1;
    if (dirty) return 2;
    if (!testResult?.ok) return 3;
    if (!enabled) return 4;
    return 5;
  })();

  const statusLabel = enabled
    ? t("adminSso.statusEnabled", {
        name: displayName.trim() || t("adminSso.statusUnnamed"),
      })
    : t("adminSso.statusDisabled");

  return (
    <div className={styles.ssoPanel}>
      <TabPanelHeader
        icon={<KeyRound size={22} />}
        title={t("adminSso.panelTitle")}
        description={t("adminSso.panelDesc")}
        actions={
          <Tag
            className={enabled ? styles.ssoStatusTagOn : styles.ssoStatusTagOff}
          >
            <span
              className={
                enabled ? styles.ssoStatusDotOn : styles.ssoStatusDotOff
              }
            />
            {statusLabel}
          </Tag>
        }
      />

      <Spin spinning={loading}>
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
                {t("login.oidcWith", {
                  name: displayName.trim() || t("adminSso.statusUnnamed"),
                })}
              </div>
              {!enabled && (
                <p className={styles.ssoPreviewHint}>
                  {t("adminSso.loginPreviewDisabled")}
                </p>
              )}
            </div>

            <section className={styles.ssoRedirectCard}>
              <div className={styles.ssoRedirectHeader}>
                <h4 className={styles.ssoSectionTitle}>
                  {t("adminSso.redirectUri")}
                </h4>
                <p className={styles.ssoSectionHint}>
                  {t("adminSso.redirectUriHint")}
                </p>
              </div>
              <Space.Compact className={styles.ssoRedirectRow}>
                <Tooltip title={redirectUri || undefined}>
                  <Input
                    readOnly
                    value={redirectUri}
                    className={styles.ssoRedirectInput}
                    placeholder={t("adminSso.redirectUriEmpty")}
                  />
                </Tooltip>
                <Button
                  type="primary"
                  icon={copied ? <Check size={15} /> : <Copy size={15} />}
                  onClick={() => void copyRedirectUri()}
                  disabled={!redirectUri}
                  aria-label={t("adminSso.copyRedirectUri")}
                >
                  {copied ? t("adminSso.copied") : t("adminSso.copy")}
                </Button>
              </Space.Compact>
              <Typography.Paragraph
                type="secondary"
                className={styles.ssoRedirectDocs}
              >
                {t("adminSso.redirectUriDocs")}
              </Typography.Paragraph>
            </section>

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
                    ? t("adminSso.testSuccess")
                    : t("adminSso.testFailed")
                }
                description={testResult.detail}
                closable
                onClose={() => setTestResult(null)}
              />
            )}
          </aside>

          <Form<SsoFormValues>
            form={form}
            layout="vertical"
            requiredMark={false}
            onFinish={(values) => void saveConfig(values)}
            onValuesChange={() => {
              if (hydratingRef.current) return;
              setDirty(true);
              setTestResult(null);
            }}
            initialValues={{
              enabled: false,
              scopes: ["openid", "profile", "email"],
            }}
            className={styles.ssoForm}
          >
            <section className={styles.ssoSection}>
              <div className={styles.ssoEnableRow}>
                <div className={styles.ssoEnableText}>
                  <div className={styles.ssoSectionTitle}>
                    {t("adminSso.enabled")}
                  </div>
                  <p className={styles.ssoSectionHint}>
                    {t("adminSso.enabledHint")}
                  </p>
                </div>
                <Form.Item
                  name="enabled"
                  valuePropName="checked"
                  className={styles.ssoEnableSwitch}
                >
                  <Switch />
                </Form.Item>
              </div>
            </section>

            <section className={styles.ssoSection}>
              <div className={styles.ssoSectionHeader}>
                <h4 className={styles.ssoSectionTitle}>
                  {t("adminSso.sectionProvider")}
                </h4>
                <p className={styles.ssoSectionHint}>
                  {t("adminSso.sectionProviderHint")}
                </p>
              </div>

              <div className={styles.ssoPresets}>
                <span className={styles.ssoPresetsLabel}>
                  {t("adminSso.presetsLabel")}
                </span>
                <div className={styles.ssoPresetChips}>
                  {IDP_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      className={[
                        styles.ssoPresetChip,
                        activePreset === preset.id
                          ? styles.ssoPresetChipActive
                          : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      onClick={() => applyPreset(preset)}
                    >
                      {t(preset.labelKey)}
                    </button>
                  ))}
                </div>
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
                getValueFromEvent={(e: ChangeEvent<HTMLInputElement>) =>
                  e.target.value
                }
              >
                <Input
                  placeholder={issuerPlaceholder}
                  onBlur={(e) => {
                    const next = normalizeIssuer(e.target.value);
                    if (next !== e.target.value) {
                      form.setFieldValue("issuer", next);
                      if (!hydratingRef.current) setDirty(true);
                    }
                  }}
                />
              </Form.Item>
            </section>

            <section className={styles.ssoSection}>
              <div className={styles.ssoSectionHeader}>
                <h4 className={styles.ssoSectionTitle}>
                  {t("adminSso.sectionCredentials")}
                </h4>
                <p className={styles.ssoSectionHint}>
                  {t("adminSso.sectionCredentialsHint")}
                </p>
              </div>
              <div className={styles.ssoFieldGrid}>
                <Form.Item
                  name="client_id"
                  label={t("adminSso.clientId")}
                  rules={[
                    {
                      required: true,
                      message: t("adminSso.clientIdRequired"),
                    },
                  ]}
                >
                  <Input autoComplete="off" />
                </Form.Item>
                <Form.Item
                  name="client_secret"
                  label={
                    <span className={styles.ssoSecretLabel}>
                      {t("adminSso.clientSecret")}
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
              </div>
              <Form.Item
                name="scopes"
                label={t("adminSso.scopes")}
                rules={[
                  {
                    validator: async (_, value: string[] | undefined) => {
                      if (!value || value.length === 0) {
                        throw new Error(t("adminSso.scopesRequired"));
                      }
                    },
                  },
                ]}
              >
                <Select
                  mode="tags"
                  tokenSeparators={[",", " "]}
                  options={SCOPE_OPTIONS}
                  placeholder={t("adminSso.scopesPlaceholder")}
                />
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
                      name="dashboard_origin"
                      label={t("adminSso.dashboardOrigin")}
                      extra={t("adminSso.dashboardOriginHint")}
                      rules={[
                        {
                          type: "url",
                          message: t("adminSso.dashboardOriginInvalid"),
                        },
                      ]}
                    >
                      <Input placeholder="https://octop.example.com" />
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
                    {t("adminSso.testHint")}
                  </span>
                )}
              </div>
            </div>
          </Form>
        </div>
      </Spin>
    </div>
  );
}
