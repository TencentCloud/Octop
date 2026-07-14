import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Drawer, Form, Input, Select, Spin, message } from "antd";
import {
  Activity,
  CheckCircle2,
  ClipboardPaste,
  ExternalLink,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import PageShell from "../../../layouts/PageShell";
import { apiErrorMessage } from "../../../utils/apiError";
import {
  connectorsApi,
  type ConnectorAuthInfo,
  type ConnectorCatalogEntry,
  type ConnectorCredentialsPreview,
  type ConnectorInstance,
  type ConnectorInstanceDetail,
} from "../../../api/modules/connectors";
import { ConnectorCard } from "./ConnectorCard";
import {
  INLINE_CREDENTIAL_GUIDE_KINDS,
  HIDE_INLINE_FIELD_GUIDE_KINDS,
  MAIL_PROVIDERS,
  mailProviderById,
} from "./connectorDefs";
import { useConnectorInstances } from "./useConnectors";
import styles from "./index.module.less";

function buildCredentials(
  entry: ConnectorCatalogEntry,
  values: Record<string, unknown>,
): Record<string, unknown> {
  const credentials: Record<string, unknown> = {};
  if (entry.auth_kind === "personal_token") {
    const token = String(values.token ?? "").trim();
    if (token) credentials.token = token;
  } else if (entry.auth_kind === "oauth2") {
    const access_token = String(values.access_token ?? "").trim();
    if (access_token && access_token !== "__configured__") {
      credentials.access_token = access_token;
    }
    if (values.refresh_token) credentials.refresh_token = values.refresh_token;
    if (values.expires_at) credentials.expires_at = values.expires_at;
    if (values.oauth_client_id)
      credentials.oauth_client_id = values.oauth_client_id;
    if (values.oauth_client_secret)
      credentials.oauth_client_secret = values.oauth_client_secret;
    if (values.openid) credentials.openid = values.openid;
  } else if (entry.auth_kind === "auth_code") {
    const code = String(values.auth_code ?? "").trim();
    if (code) credentials.code = code;
  } else if (entry.auth_kind === "api_key") {
    const api_key = String(values.api_key ?? "").trim();
    if (api_key) credentials.api_key = api_key;
    if (entry.kind === "tencent-ima" && values.client_id) {
      credentials.client_id = values.client_id;
    }
    if (entry.kind === "tencent-lexiang" && values.client_id) {
      credentials.client_id = values.client_id;
    }
  } else if (entry.auth_kind === "imap_app_password") {
    credentials.email = values.email;
    const password = String(values.password ?? "").trim();
    if (password) credentials.password = password;
    if (values.mail_provider) {
      credentials.mail_provider = values.mail_provider;
    }
    if (values.mail_provider === "custom") {
      if (values.imap_host) credentials.imap_host = values.imap_host;
      if (values.smtp_host) credentials.smtp_host = values.smtp_host;
    }
  } else if (entry.auth_kind === "api_credentials") {
    credentials.app_id = values.app_id;
    credentials.sdk_id = values.sdk_id;
    const secret_key = String(values.secret_key ?? "").trim();
    if (secret_key) credentials.secret_key = secret_key;
  }
  return credentials;
}

function previewToFormValues(
  entry: ConnectorCatalogEntry,
  detail: ConnectorInstanceDetail | null,
): Record<string, unknown> {
  if (!detail) {
    return { display_name: entry.name, mail_provider: "qq" };
  }
  const preview = detail.credentials_preview ?? {};
  const values: Record<string, unknown> = {
    display_name: detail.display_name || entry.name,
  };
  if (preview.email) values.email = preview.email;
  if (preview.mail_provider) values.mail_provider = preview.mail_provider;
  if (preview.imap_host) values.imap_host = preview.imap_host;
  if (preview.smtp_host) values.smtp_host = preview.smtp_host;
  if (preview.bkn) values.bkn = preview.bkn;
  if (preview.knowledge_base_id)
    values.knowledge_base_id = preview.knowledge_base_id;
  if (preview.app_id) values.app_id = preview.app_id;
  if (preview.client_id) values.client_id = preview.client_id;
  if (preview.sdk_id) values.sdk_id = preview.sdk_id;
  if (entry.auth_kind === "oauth2" && preview.oauth_configured) {
    values.access_token = "__configured__";
  }
  return values;
}

function hasFreshCredentialInput(
  entry: ConnectorCatalogEntry,
  values: Record<string, unknown>,
): boolean {
  if (entry.auth_kind === "personal_token") {
    return Boolean(String(values.token ?? "").trim());
  }
  if (entry.auth_kind === "oauth2") {
    const token = String(values.access_token ?? "").trim();
    return Boolean(token && token !== "__configured__");
  }
  if (entry.auth_kind === "auth_code") {
    return Boolean(String(values.auth_code ?? "").trim());
  }
  if (entry.auth_kind === "api_key") {
    return Boolean(String(values.api_key ?? "").trim());
  }
  if (entry.auth_kind === "imap_app_password") {
    return Boolean(String(values.password ?? "").trim());
  }
  if (entry.auth_kind === "api_credentials") {
    return Boolean(String(values.secret_key ?? "").trim());
  }
  return false;
}

function openAuthorizeLabel(
  kind: string,
  t: (key: string, fallback: string) => string,
): string {
  if (kind === "tencent-ima") {
    return t("connectors.openAuthorizePage", "打开授权页");
  }
  return t("connectors.openTokenPage", "打开授权页");
}

function authCodeGuideLabel(
  kind: string,
  t: (key: string, fallback: string) => string,
): string {
  if (kind === "tencent-news") {
    return t("connectors.newsAuthGuide", "如何获取腾讯新闻 API Key");
  }
  return t("connectors.authCodeDoc", "查看如何获取授权码");
}

function secretFieldRules(required: boolean) {
  const trimRule = {
    validator: (_: unknown, value: unknown) => {
      const text = String(value ?? "").trim();
      if (required && !text) {
        return Promise.reject(new Error(""));
      }
      return Promise.resolve();
    },
  };
  return required ? [{ required: true, message: "" }, trimRule] : [trimRule];
}

function configuredExtra(
  preview: ConnectorCredentialsPreview | undefined,
  key: keyof ConnectorCredentialsPreview,
  t: (key: string, fallback: string) => string,
) {
  if (!preview?.[key]) return undefined;
  return t("connectors.secretConfigured", "已配置，留空表示不修改");
}

function ConnectorConfigDrawer({
  open,
  entry,
  instance,
  onClose,
  onSaved,
}: {
  open: boolean;
  entry: ConnectorCatalogEntry | null;
  instance: ConnectorInstance | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [authInfo, setAuthInfo] = useState<ConnectorAuthInfo | null>(null);
  const [instanceDetail, setInstanceDetail] =
    useState<ConnectorInstanceDetail | null>(null);
  const [probeResult, setProbeResult] = useState<
    { name: string; description: string }[] | null
  >(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const hasStoredCredentials = Boolean(instance?.has_credentials);
  const mailProvider = Form.useWatch("mail_provider", form) ?? "qq";
  const selectedMailProvider = mailProviderById(String(mailProvider));

  useEffect(() => {
    if (!open || !entry) return;
    setShowManual(false);
    setAuthInfo(null);
    setInstanceDetail(null);
    setProbeResult(null);
    form.resetFields();
    form.setFieldsValue({ display_name: entry.name });

    void connectorsApi
      .authInfo(entry.kind)
      .then(setAuthInfo)
      .catch(() => {
        setAuthInfo({
          authorize_url: entry.quick_auth_url ?? null,
          login_url: entry.login_url ?? null,
          guide_url: entry.guide_url ?? entry.doc_url ?? null,
          manual_url:
            entry.manual_url ?? entry.guide_url ?? entry.doc_url ?? null,
          auth_hint: entry.auth_hint ?? null,
        });
      });

    if (instance) {
      setLoadingDetail(true);
      void connectorsApi
        .getInstance(instance.instance_id)
        .then((detail) => {
          setInstanceDetail(detail);
          form.setFieldsValue(previewToFormValues(entry, detail));
          if (detail.credentials_preview?.oauth_configured) {
            setShowManual(false);
          }
        })
        .catch(() => {
          form.setFieldsValue({
            display_name: instance.display_name || entry.name,
          });
        })
        .finally(() => setLoadingDetail(false));
    }
  }, [open, entry, instance, form]);

  const openUrl = (url: string | null | undefined) => {
    if (!url) return;
    window.open(url, "octop-connector-auth", "width=720,height=800");
  };

  const handleOpenAuthorize = () => {
    openUrl(authInfo?.authorize_url);
  };

  const handleOpenLogin = () => {
    openUrl(authInfo?.login_url);
  };

  const extractPastedCredential = (text: string): string => {
    const trimmed = text.trim();
    try {
      const url = new URL(trimmed);
      const fromQuery =
        url.searchParams.get("code") ??
        url.searchParams.get("access_token") ??
        url.searchParams.get("token");
      if (fromQuery) return fromQuery;
    } catch {
      // not a full URL
    }
    const match = trimmed.match(/access_token=([^&\s#]+)/i);
    if (match?.[1]) {
      try {
        return decodeURIComponent(match[1]);
      } catch {
        return match[1];
      }
    }
    const mcpMatch = trimmed.match(/mcp_token=([^\s;,&"']+)/i);
    if (mcpMatch?.[1]) {
      return mcpMatch[1];
    }
    return trimmed;
  };

  const handlePasteToken = async () => {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (!text) {
        message.warning(t("connectors.clipboardEmpty", "剪贴板为空"));
        return;
      }
      if (entry?.auth_kind === "personal_token") {
        form.setFieldValue("token", extractPastedCredential(text));
      } else if (entry?.auth_kind === "auth_code") {
        form.setFieldValue("auth_code", text);
      } else if (entry?.auth_kind === "api_key") {
        form.setFieldValue("api_key", text);
      }
      message.success(t("connectors.pasteSuccess", "已粘贴"));
    } catch {
      message.error(
        t("connectors.clipboardDenied", "无法读取剪贴板，请手动粘贴"),
      );
    }
  };

  const handleOAuth = async () => {
    if (!entry) return;
    try {
      const { authorize_url, state_id } = await connectorsApi.oauthStart(
        entry.kind,
        "/connectors",
      );
      const popup = window.open(
        authorize_url,
        "octop-oauth",
        "width=520,height=720",
      );
      const onMessage = async (ev: MessageEvent) => {
        if (ev.data?.type !== "octop:connector-oauth") return;
        if (ev.data.state_id !== state_id) return;
        window.removeEventListener("message", onMessage);
        popup?.close();
        try {
          const pending = await connectorsApi.oauthPending(state_id);
          const tokens = pending.tokens ?? {};
          form.setFieldsValue({
            display_name: entry.name,
            access_token: tokens.access_token,
            refresh_token: tokens.refresh_token,
            expires_at: tokens.expires_at,
            oauth_client_id: tokens.oauth_client_id,
            oauth_client_secret: tokens.oauth_client_secret,
            openid: tokens.openid,
          });
          message.success(t("connectors.oauthSuccess", "授权成功，请保存连接"));
        } catch {
          message.error(t("connectors.oauthFailed", "获取授权结果失败"));
        }
      };
      window.addEventListener("message", onMessage);
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.oauthStartFailed", "无法启动 OAuth")),
      );
    }
  };

  const handleProbe = async () => {
    if (!entry) return;
    const values = form.getFieldsValue();
    const freshInput = hasFreshCredentialInput(entry, values);
    const canUseStored = hasStoredCredentials && instance && !freshInput;

    if (!canUseStored) {
      try {
        await form.validateFields();
      } catch {
        message.warning(
          t("connectors.probeNeedConfig", "请先填写连接配置后再探测"),
        );
        return;
      }
    }

    setProbing(true);
    setProbeResult(null);
    try {
      const r = canUseStored
        ? await connectorsApi.testInstance(instance.instance_id)
        : await connectorsApi.testCredentials({
            kind: entry.kind,
            credentials: buildCredentials(entry, values),
          });
      if (r.ok) {
        const tools = r.tools ?? [];
        setProbeResult(tools);
      } else {
        setProbeResult(null);
        message.error(r.error ?? t("connectors.probeFailed", "探测失败"));
      }
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.probeFailed", "探测失败"), t),
      );
    } finally {
      setProbing(false);
    }
  };

  const handleSubmit = async () => {
    if (!entry) return;
    try {
      await form.validateFields();
    } catch {
      return;
    }
    const values = form.getFieldsValue();
    if (entry.auth_kind === "oauth2") {
      const token = String(values.access_token ?? "").trim();
      if (!hasStoredCredentials && !token) {
        message.warning(
          t("connectors.oauthNeedToken", "请先完成授权或手动填写 Token"),
        );
        return;
      }
    }
    setSaving(true);
    try {
      const payload = buildCredentials(entry, values);
      await connectorsApi.createInstance({
        kind: entry.kind,
        display_name: values.display_name as string,
        credentials: payload,
      });
      message.success(
        hasStoredCredentials
          ? t("connectors.saveSuccess", "连接器已保存")
          : t("connectors.createSuccess", "连接器已创建"),
      );
      onSaved();
      onClose();
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.createFailed", "创建失败"), t),
      );
    } finally {
      setSaving(false);
    }
  };

  if (!entry) return null;

  const hasOAuthPopup = entry.auth_kind === "oauth2" && entry.oauth_ready;
  const hasAuthorizeUrl = Boolean(authInfo?.authorize_url);
  const hasLoginUrl = Boolean(authInfo?.login_url);
  const guideUrl = authInfo?.guide_url ?? entry.guide_url ?? entry.doc_url;
  const manualUrl = authInfo?.manual_url ?? entry.manual_url ?? guideUrl;
  const authHint = authInfo?.auth_hint ?? entry.auth_hint;

  const preview = instanceDetail?.credentials_preview;
  const secretRequired = !hasStoredCredentials;
  const hideTopAuth = entry
    ? INLINE_CREDENTIAL_GUIDE_KINDS.has(entry.kind)
    : false;
  const hideFieldGuide = entry
    ? HIDE_INLINE_FIELD_GUIDE_KINDS.has(entry.kind)
    : false;
  const hideGuideLink =
    hideTopAuth ||
    Boolean(entry?.quick_auth_url && guideUrl === entry.quick_auth_url);

  return (
    <Drawer
      title={
        hasStoredCredentials
          ? t("connectors.editConnection", {
              name: entry.name,
              defaultValue: `配置 ${entry.name}`,
            })
          : t("connectors.configureConnection", {
              name: entry.name,
              defaultValue: `配置 ${entry.name}`,
            })
      }
      open={open}
      onClose={onClose}
      width={440}
      destroyOnClose
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            icon={<Activity size={14} />}
            loading={probing}
            onClick={() => void handleProbe()}
          >
            {t("connectors.probe", "探测")}
          </Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void handleSubmit()}
          >
            {t("common.save")}
          </Button>
        </div>
      }
    >
      <div className={styles.drawerBody}>
        {loadingDetail ? (
          <div className={styles.drawerLoading}>
            <Spin size="small" />
          </div>
        ) : null}

        {authHint && <div className={styles.authHint}>{authHint}</div>}

        {guideUrl && !hideGuideLink && (
          <div className={styles.guideLinks}>
            <a href={guideUrl} target="_blank" rel="noreferrer">
              {t("connectors.viewGuide", "查看获取说明")}
            </a>
          </div>
        )}

        <div className={styles.quickAuthBar}>
          {hasOAuthPopup && (
            <Button
              type="primary"
              icon={<Sparkles size={14} />}
              onClick={() => void handleOAuth()}
            >
              {t("connectors.oneClickOAuth", "一键授权")}
            </Button>
          )}
          {hasAuthorizeUrl && !hideTopAuth && (
            <Button
              type="primary"
              icon={<ExternalLink size={14} />}
              onClick={handleOpenAuthorize}
            >
              {t("connectors.openAuthorizePage", "打开授权页")}
            </Button>
          )}
          {hasLoginUrl && !hideTopAuth && (
            <Button icon={<ExternalLink size={14} />} onClick={handleOpenLogin}>
              {t("connectors.openLoginPage", "打开登录页")}
            </Button>
          )}
          {!hideTopAuth &&
            !hasAuthorizeUrl &&
            !hasLoginUrl &&
            entry.quick_auth_url &&
            entry.auth_kind !== "oauth2" && (
              <Button
                type="primary"
                icon={<ExternalLink size={14} />}
                onClick={() => openUrl(entry.quick_auth_url)}
              >
                {openAuthorizeLabel(entry.kind, t)}
              </Button>
            )}
          {(entry.auth_kind === "personal_token" ||
            entry.auth_kind === "auth_code" ||
            entry.auth_kind === "api_key") && (
            <Button
              icon={<ClipboardPaste size={14} />}
              onClick={() => void handlePasteToken()}
            >
              {t("connectors.pasteFromClipboard", "从剪贴板粘贴")}
            </Button>
          )}
        </div>

        <Form form={form} layout="vertical">
          <div className={styles.configSectionTitle}>
            {t("connectors.configSection", "连接配置")}
          </div>
          <Form.Item
            name="display_name"
            label={t("connectors.displayName", "显示名称")}
            rules={[{ required: true }]}
          >
            <Input placeholder={entry.name} />
          </Form.Item>

          {entry.auth_kind === "personal_token" && (
            <Form.Item
              name="token"
              label={t("connectors.token", "访问 Token")}
              rules={secretFieldRules(secretRequired)}
              extra={
                configuredExtra(preview, "token_configured", t) ??
                (manualUrl ? (
                  <a href={manualUrl} target="_blank" rel="noreferrer">
                    {t("connectors.getTokenAt", "前往获取 Token")}
                  </a>
                ) : (
                  <a href={entry.doc_url} target="_blank" rel="noreferrer">
                    {t("connectors.getToken", "获取 Token")}
                  </a>
                ))
              }
            >
              <Input.Password
                placeholder={hasStoredCredentials ? "••••••••" : undefined}
              />
            </Form.Item>
          )}

          {entry.auth_kind === "auth_code" && (
            <>
              <Form.Item
                name="auth_code"
                label={t("connectors.authCode", "授权码")}
                rules={secretFieldRules(secretRequired)}
                extra={
                  configuredExtra(preview, "auth_configured", t) ??
                  (!hideFieldGuide && entry.manual_url ? (
                    <a href={entry.manual_url} target="_blank" rel="noreferrer">
                      {authCodeGuideLabel(entry.kind, t)}
                    </a>
                  ) : !hideFieldGuide && manualUrl ? (
                    <a href={manualUrl} target="_blank" rel="noreferrer">
                      {authCodeGuideLabel(entry.kind, t)}
                    </a>
                  ) : undefined)
                }
              >
                <Input.Password
                  placeholder={
                    hasStoredCredentials
                      ? t("connectors.secretPlaceholder", "留空表示不修改")
                      : t("connectors.authCodePlaceholder", "粘贴授权码")
                  }
                />
              </Form.Item>
            </>
          )}

          {entry.auth_kind === "api_key" && (
            <>
              <Form.Item
                name="api_key"
                label={t("connectors.apiKey", "API Key")}
                rules={secretFieldRules(secretRequired)}
                extra={
                  configuredExtra(preview, "api_key_configured", t) ??
                  (!hideFieldGuide && manualUrl ? (
                    <a href={manualUrl} target="_blank" rel="noreferrer">
                      {t("connectors.apiKeyDoc", "查看如何获取 API Key")}
                    </a>
                  ) : undefined)
                }
              >
                <Input.Password
                  placeholder={
                    hasStoredCredentials
                      ? t("connectors.secretPlaceholder", "留空表示不修改")
                      : entry.kind === "tencent-ima"
                      ? t(
                          "connectors.imaApiKeyPlaceholder",
                          "从 IMA 配置页复制（仅展示一次）",
                        )
                      : t("connectors.apiKeyPlaceholder", "粘贴 API Key")
                  }
                />
              </Form.Item>
              {entry.kind === "tencent-ima" && (
                <Form.Item
                  name="client_id"
                  label="Client ID"
                  rules={[{ required: true }]}
                >
                  <Input
                    placeholder={t(
                      "connectors.imaClientIdPlaceholder",
                      "从 IMA 配置页复制",
                    )}
                  />
                </Form.Item>
              )}
              {entry.kind === "tencent-lexiang" && (
                <Form.Item
                  name="client_id"
                  label={t(
                    "connectors.lexiangCompanyFrom",
                    "企业标识 (company_from)",
                  )}
                  rules={[{ required: true }]}
                >
                  <Input
                    placeholder={t(
                      "connectors.lexiangCompanyFromPlaceholder",
                      "从乐享凭证页复制",
                    )}
                  />
                </Form.Item>
              )}
            </>
          )}

          {entry.auth_kind === "oauth2" && (
            <>
              <Form.Item name="access_token" hidden>
                <Input />
              </Form.Item>
              <Form.Item name="refresh_token" hidden>
                <Input />
              </Form.Item>
              <Form.Item name="expires_at" hidden>
                <Input />
              </Form.Item>
              <Form.Item name="oauth_client_id" hidden>
                <Input />
              </Form.Item>
              <Form.Item name="oauth_client_secret" hidden>
                <Input />
              </Form.Item>
              <Form.Item name="openid" hidden>
                <Input />
              </Form.Item>
              {preview?.oauth_configured && !showManual && (
                <div className={styles.configuredBadge}>
                  {t("connectors.oauthConfigured", "已授权，可直接探测或保存")}
                </div>
              )}
              {entry.oauth_ready && !preview?.oauth_configured && (
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--fn-text-tertiary)",
                    marginBottom: 8,
                  }}
                >
                  {t(
                    "connectors.oauthHint",
                    "点击「一键授权」完成登录后保存即可",
                  )}
                </div>
              )}
              <div
                className={styles.manualToggle}
                onClick={() => setShowManual((v) => !v)}
                role="button"
                tabIndex={0}
              >
                {showManual
                  ? t("connectors.hideManual", "收起手动输入")
                  : t("connectors.showManual", "手动粘贴 Token")}
              </div>
              {showManual && (
                <Form.Item
                  name="access_token_manual"
                  label={t("connectors.accessTokenManual", "Access Token")}
                  extra={
                    manualUrl ? (
                      <a href={manualUrl} target="_blank" rel="noreferrer">
                        {t("connectors.manualTokenDoc", "手动获取 Token 文档")}
                      </a>
                    ) : undefined
                  }
                >
                  <Input.Password
                    onChange={(e) =>
                      form.setFieldValue("access_token", e.target.value)
                    }
                  />
                </Form.Item>
              )}
            </>
          )}

          {entry.auth_kind === "imap_app_password" && (
            <>
              <Form.Item
                name="mail_provider"
                label={t("connectors.mailProvider", "邮箱服务商")}
                initialValue="qq"
              >
                <Select
                  options={MAIL_PROVIDERS.map((item) => ({
                    value: item.id,
                    label: item.label,
                  }))}
                />
              </Form.Item>
              <Form.Item
                name="email"
                label={t("connectors.email", "邮箱地址")}
                rules={[{ required: true }]}
              >
                <Input placeholder={selectedMailProvider.emailPlaceholder} />
              </Form.Item>
              <Form.Item
                name="password"
                label={t("connectors.authCode", "授权码")}
                rules={secretFieldRules(secretRequired)}
                extra={
                  configuredExtra(preview, "password_configured", t) ??
                  (selectedMailProvider.guideUrl ? (
                    <a
                      href={selectedMailProvider.guideUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t(
                        "connectors.personalMailAuthGuide",
                        "如何获取邮箱授权码",
                      )}
                    </a>
                  ) : undefined)
                }
              >
                <Input.Password
                  placeholder={
                    hasStoredCredentials
                      ? t("connectors.secretPlaceholder", "留空表示不修改")
                      : undefined
                  }
                />
              </Form.Item>
              {mailProvider === "custom" && (
                <>
                  <Form.Item
                    name="imap_host"
                    label={t("connectors.imapHost", "IMAP 服务器")}
                    rules={[{ required: true }]}
                  >
                    <Input placeholder="imap.example.com" />
                  </Form.Item>
                  <Form.Item
                    name="smtp_host"
                    label={t("connectors.smtpHost", "SMTP 服务器")}
                    rules={[{ required: true }]}
                  >
                    <Input placeholder="smtp.example.com" />
                  </Form.Item>
                </>
              )}
            </>
          )}

          {entry.auth_kind === "api_credentials" && (
            <>
              <Form.Item
                name="app_id"
                label="AppId"
                rules={[{ required: true }]}
              >
                <Input placeholder="企业 ID / AppId" />
              </Form.Item>
              <Form.Item
                name="sdk_id"
                label="SdkId"
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="secret_key"
                label="Secret"
                rules={secretFieldRules(secretRequired)}
                extra={configuredExtra(preview, "secret_key_configured", t)}
              >
                <Input.Password
                  placeholder={
                    hasStoredCredentials
                      ? t("connectors.secretPlaceholder", "留空表示不修改")
                      : undefined
                  }
                />
              </Form.Item>
            </>
          )}
        </Form>

        {probeResult !== null && (
          <div className={styles.probeResult}>
            <div className={styles.probeResultHeader}>
              <CheckCircle2
                size={18}
                className={styles.probeResultIcon}
                aria-hidden
              />
              <div className={styles.probeResultMeta}>
                <div className={styles.probeResultTitle}>
                  {t("connectors.probeToolsTitle", "探测成功")}
                </div>
                <div className={styles.probeResultSubtitle}>
                  {probeResult.length > 0
                    ? t("connectors.probeToolsHint", {
                        count: probeResult.length,
                        defaultValue: `连接正常，获取以下工具列表（共 ${probeResult.length} 个）`,
                      })
                    : t(
                        "connectors.probeToolsEmpty",
                        "连接正常，但未发现可用工具",
                      )}
                </div>
              </div>
            </div>
            {probeResult.length > 0 && (
              <ul className={styles.probeToolList}>
                {probeResult.map((tool, index) => (
                  <li key={tool.name} className={styles.probeToolItem}>
                    <span className={styles.probeToolIndex}>{index + 1}</span>
                    <div className={styles.probeToolBody}>
                      <div className={styles.probeToolName}>{tool.name}</div>
                      {tool.description ? (
                        <div className={styles.probeToolDesc}>
                          {tool.description}
                        </div>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Drawer>
  );
}

export default function ConnectorsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [drawerEntry, setDrawerEntry] = useState<ConnectorCatalogEntry | null>(
    null,
  );
  const [drawerInstance, setDrawerInstance] =
    useState<ConnectorInstance | null>(null);
  const { catalog, instances, loading, refresh } = useConnectorInstances();

  const instanceByKind = useMemo(() => {
    const map = new Map<string, ConnectorInstance>();
    for (const inst of instances) {
      if (!map.has(inst.kind)) {
        map.set(inst.kind, inst);
      }
    }
    return map;
  }, [instances]);

  useEffect(() => {
    const oauthState = searchParams.get("oauth_state");
    if (!oauthState) return;
    void (async () => {
      try {
        const pending = await connectorsApi.oauthPending(oauthState);
        setDrawerEntry(catalog.find((c) => c.kind === pending.kind) ?? null);
        setDrawerInstance(null);
        message.info(
          t("connectors.oauthCompleteHint", "请填写显示名称并保存连接"),
        );
      } catch {
        message.error(t("connectors.oauthFailed", "获取授权结果失败"));
      }
      searchParams.delete("oauth_state");
      setSearchParams(searchParams, { replace: true });
    })();
  }, [searchParams, setSearchParams, catalog, t]);

  const handleConfigure = useCallback(
    (entry: ConnectorCatalogEntry, instance: ConnectorInstance | null) => {
      setDrawerEntry(entry);
      setDrawerInstance(instance);
    },
    [],
  );

  const handleToggleEnabled = useCallback(
    async (instance: ConnectorInstance, enabled: boolean) => {
      try {
        await connectorsApi.patchInstance(instance.instance_id, {
          status: enabled ? "active" : "disabled",
        });
        await refresh();
        message.success(
          enabled
            ? t("connectors.enableSuccess", "已启用")
            : t("connectors.disableSuccess", "已停用"),
        );
      } catch (e) {
        console.error(e);
        message.error(t("connectors.toggleFailed", "更新失败"));
      }
    },
    [refresh, t],
  );

  const handleSaved = useCallback(async () => {
    await refresh();
  }, [refresh]);

  const handleCloseDrawer = useCallback(() => {
    setDrawerEntry(null);
    setDrawerInstance(null);
  }, []);

  return (
    <PageShell
      title={t("pageShell.connectors.title")}
      subtitle={t("pageShell.connectors.subtitle")}
    >
      <div className={styles.connectorsPage}>
        {loading ? (
          <div className={styles.loadingState}>
            <Spin />
          </div>
        ) : (
          <div className={styles.typeGrid}>
            {catalog.map((entry) => (
              <ConnectorCard
                key={entry.kind}
                entry={entry}
                instance={instanceByKind.get(entry.kind) ?? null}
                onConfigure={handleConfigure}
                onToggleEnabled={(inst, enabled) =>
                  void handleToggleEnabled(inst, enabled)
                }
              />
            ))}
          </div>
        )}
      </div>

      <ConnectorConfigDrawer
        open={drawerEntry !== null}
        entry={drawerEntry}
        instance={drawerInstance}
        onClose={handleCloseDrawer}
        onSaved={() => void handleSaved()}
      />
    </PageShell>
  );
}
