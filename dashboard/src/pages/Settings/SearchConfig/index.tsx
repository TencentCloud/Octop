import { useEffect, useRef, useState, useCallback } from "react";
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Spin,
  Switch,
  Typography,
} from "antd";

import {
  Activity,
  Check,
  CheckCircle,
  KeyRound,
  Search,
  Settings2,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { envsApi } from "../../../api/modules/env";
import api from "../../../api";
import { customProviderLogo, getProviderLogo } from "../../../assets/providers";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { apiErrorMessage } from "../../../utils/apiError";
import { userCan } from "../../../utils/permissions";
import styles from "./index.module.less";

const { Text } = Typography;

type SearchFieldKind = "password" | "text" | "number" | "switch";

interface SearchField {
  key: string;
  kind: SearchFieldKind;
  /** i18n key for the form label; falls back to the raw env key. */
  labelKey?: string;
  required?: boolean;
  placeholder?: string;
  hintKey?: string;
}

interface SearchProvider {
  id: string;
  name: string;
  descriptionKey: string;
  docs_url?: string;
  /** Legacy providers: every listed key is required (rendered as secret fields). */
  required_keys: string[];
  /** Rich config form for providers with more than an API key. */
  fields?: SearchField[];
  /** Extra keys that also mark the provider configured (e.g. a shared fallback). */
  fallback_keys?: string[];
  /** Show the "reuse the DeepSeek model provider key" button. */
  reuse_model_key?: boolean;
  configured: boolean;
}

const SEARCH_PROVIDERS: SearchProvider[] = [
  {
    id: "tavily",
    name: "Tavily",
    descriptionKey: "setupWizard.search.providers.tavily.desc",
    docs_url: "https://app.tavily.com/",
    required_keys: ["TAVILY_API_KEY"],
    configured: false,
  },
  {
    id: "brave",
    name: "Brave Search",
    descriptionKey: "setupWizard.search.providers.brave.desc",
    docs_url: "https://api.search.brave.com/",
    required_keys: ["BRAVE_API_KEY"],
    configured: false,
  },
  {
    id: "deepseek",
    name: "DeepSeek Search",
    descriptionKey: "setupWizard.search.providers.deepseek.desc",
    docs_url: "https://api-docs.deepseek.com/guides/search/",
    required_keys: ["DEEPSEEK_API_KEY"],
    fallback_keys: ["DEEPSEEK_SEARCH_API_KEY"],
    reuse_model_key: true,
    fields: [
      {
        key: "DEEPSEEK_API_KEY",
        kind: "password",
        labelKey: "setupWizard.search.deepseek.apiKey",
        required: true,
      },
      {
        key: "DEEPSEEK_SEARCH_BASE_URL",
        kind: "text",
        labelKey: "setupWizard.search.deepseek.baseUrl",
        placeholder: "https://api.deepseek.com",
      },
      {
        key: "DEEPSEEK_SEARCH_COUNT",
        kind: "number",
        labelKey: "setupWizard.search.deepseek.count",
        placeholder: "10",
        hintKey: "setupWizard.search.deepseek.countHint",
      },
      {
        key: "DEEPSEEK_SEARCH_NEED_CONTENT",
        kind: "switch",
        labelKey: "setupWizard.search.deepseek.needContent",
        hintKey: "setupWizard.search.deepseek.needContentHint",
      },
      {
        key: "DEEPSEEK_SEARCH_LOCALIZATION",
        kind: "text",
        labelKey: "setupWizard.search.deepseek.localization",
        hintKey: "setupWizard.search.deepseek.localizationHint",
      },
    ],
    configured: false,
  },
  {
    id: "google",
    name: "Google Search",
    descriptionKey: "setupWizard.search.providers.google.desc",
    docs_url: "https://programmablesearchengine.google.com/",
    required_keys: ["GOOGLE_API_KEY", "GOOGLE_CSE_ID"],
    configured: false,
  },
  {
    id: "kimi",
    name: "Kimi (Moonshot)",
    descriptionKey: "setupWizard.search.providers.kimi.desc",
    docs_url: "https://platform.moonshot.cn/",
    required_keys: ["MOONSHOT_API_KEY"],
    configured: false,
  },
  {
    id: "yuanbao",
    name: "元宝搜索",
    descriptionKey: "setupWizard.search.providers.yuanbao.desc",
    docs_url: "https://cloud.tencent.com/document/product/1806/130615",
    required_keys: ["TENCENTCLOUD_WSA_APIKEY"],
    configured: false,
  },
];

function searchProviderLogo(providerId: string): string {
  return getProviderLogo(providerId) ?? customProviderLogo;
}

function providerFields(provider: SearchProvider): SearchField[] {
  if (provider.fields && provider.fields.length > 0) {
    return provider.fields;
  }
  return provider.required_keys.map((key) => ({
    key,
    kind: "password" as const,
    required: true,
  }));
}

function isTruthyEnv(value: string | undefined): boolean {
  if (!value) return false;
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}

function providerEnvKeys(provider: SearchProvider): string[] {
  return [
    ...new Set([
      ...provider.required_keys,
      ...(provider.fallback_keys ?? []),
      ...(provider.fields ?? []).map((field) => field.key),
    ]),
  ];
}

function isProviderConfigured(
  provider: SearchProvider,
  envVars: Record<string, string>,
): boolean {
  if (provider.required_keys.every((key) => (envVars[key] ?? "").trim())) {
    return true;
  }
  return (provider.fallback_keys ?? []).some((key) =>
    (envVars[key] ?? "").trim(),
  );
}

function initialFieldValues(
  provider: SearchProvider,
  envVars: Record<string, string>,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const field of providerFields(provider)) {
    let raw: string | undefined = envVars[field.key];
    if (
      (raw === undefined || raw === "") &&
      provider.required_keys.includes(field.key)
    ) {
      raw = (provider.fallback_keys ?? [])
        .map((key) => envVars[key])
        .find((value) => !!value);
    }
    if (field.kind === "switch") {
      values[field.key] = isTruthyEnv(raw);
    } else if (raw !== undefined && raw !== "") {
      values[field.key] = raw;
    }
  }
  return values;
}

/** Convert form values into the env map used for probing / saving. */
function collectFieldEnvs(
  provider: SearchProvider,
  values: Record<string, unknown>,
  base: Record<string, string>,
): Record<string, string> {
  const out = { ...base };
  for (const field of providerFields(provider)) {
    const raw = values[field.key];
    if (field.kind === "switch") {
      out[field.key] = raw ? "true" : "false";
      continue;
    }
    const value = raw === undefined || raw === null ? "" : String(raw).trim();
    if (value) {
      out[field.key] = value;
    } else {
      delete out[field.key];
    }
  }
  return out;
}

interface ConfigureDrawerProps {
  provider: SearchProvider;
  envVars: Record<string, string>;
  open: boolean;
  canReuseModelKey: boolean;
  onClose: () => void;
  onSaved: () => void;
}

function ConfigureDrawer({
  provider,
  envVars,
  open,
  canReuseModelKey,
  onClose,
  onSaved,
}: ConfigureDrawerProps) {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [reusingKey, setReusingKey] = useState(false);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue(initialFieldValues(provider, envVars));
  }, [envVars, provider, form, open]);

  const handleSave = async () => {
    try {
      setSaving(true);
      const values = (await form.validateFields()) as Record<string, unknown>;
      const allEnvs = collectFieldEnvs(provider, values, envVars);
      await envsApi.batchSaveEnvs(allEnvs);
      message.success(
        t("setupWizard.search.saveSuccess", { name: provider.name }),
      );
      onSaved();
      onClose();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(apiErrorMessage(err, t("setupWizard.search.saveFailed")));
    } finally {
      setSaving(false);
    }
  };

  const handleProbe = async () => {
    try {
      setTesting(true);
      const values = (await form.validateFields()) as Record<string, unknown>;
      const testEnvs = collectFieldEnvs(provider, values, envVars);
      const result = await api.testSearch(provider.id, testEnvs);
      if (result.success) {
        message.success(
          t("setupWizard.search.testSuccess", { name: provider.name }),
        );
      } else {
        message.error(
          t("setupWizard.search.testFailed", {
            name: provider.name,
            error: result.error || result.error_type || "Unknown error",
          }),
        );
      }
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        t("setupWizard.search.testFailed", {
          name: provider.name,
          error: apiErrorMessage(err, String(err)),
        }),
      );
    } finally {
      setTesting(false);
    }
  };

  const handleReuseModelKey = async () => {
    try {
      setReusingKey(true);
      const result = await api.importDeepSeekModelKey();
      if (result.ok) {
        message.success(
          t("setupWizard.search.deepseek.reuseSuccess", {
            name: result.provider_name || "DeepSeek",
          }),
        );
        onSaved();
      } else {
        message.warning(t("setupWizard.search.deepseek.reuseMissing"));
      }
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("setupWizard.search.deepseek.reuseFailed")),
      );
    } finally {
      setReusingKey(false);
    }
  };

  const handleRevoke = () => {
    modal.confirm({
      title: t("setupWizard.search.revokeTitle", { name: provider.name }),
      content: t("setupWizard.search.revokeConfirm", { name: provider.name }),
      okText: t("setupWizard.search.revoke"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          setRevoking(true);
          const remaining = { ...envVars };
          for (const key of providerEnvKeys(provider)) {
            delete remaining[key];
          }
          await envsApi.batchSaveEnvs(remaining);
          message.success(
            t("setupWizard.search.revokeSuccess", { name: provider.name }),
          );
          onSaved();
          onClose();
        } catch (err) {
          message.error(
            apiErrorMessage(err, t("setupWizard.search.revokeFailed")),
          );
        } finally {
          setRevoking(false);
        }
      },
    });
  };

  const fields = providerFields(provider);

  return (
    <Drawer
      title={t("advancedSettings.search.configureTitle", {
        name: provider.name,
      })}
      open={open}
      onClose={onClose}
      width={440}
      placement="right"
      destroyOnHidden
      footer={
        <div className={styles.drawerFooter}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            icon={<Activity size={14} />}
            loading={testing}
            onClick={() => void handleProbe()}
          >
            {t("advancedSettings.search.probe")}
          </Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void handleSave()}
          >
            {t("common.save")}
          </Button>
        </div>
      }
    >
      <div className={styles.drawerHint}>{t(provider.descriptionKey)}</div>
      {provider.reuse_model_key && canReuseModelKey ? (
        <div className={styles.reuseRow}>
          <Button
            size="small"
            icon={<KeyRound size={14} />}
            loading={reusingKey}
            onClick={() => void handleReuseModelKey()}
          >
            {t("setupWizard.search.deepseek.reuseModelKey")}
          </Button>
          <span className={styles.reuseHint}>
            {t("setupWizard.search.deepseek.reuseHint")}
          </span>
        </div>
      ) : null}
      <Form form={form} layout="vertical" requiredMark={false}>
        {fields.map((field) => {
          const label = field.labelKey ? t(field.labelKey) : field.key;
          const extra = field.hintKey ? t(field.hintKey) : undefined;
          const hintLink =
            !provider.fields &&
            field.key === provider.required_keys[0] &&
            provider.docs_url ? (
              <a
                href={provider.docs_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("setupWizard.search.getApiKey")}
              </a>
            ) : undefined;
          return (
            <Form.Item
              key={field.key}
              name={field.key}
              label={label}
              valuePropName={field.kind === "switch" ? "checked" : undefined}
              rules={
                field.required
                  ? [
                      {
                        required: true,
                        message: t("setupWizard.search.required", {
                          key: field.labelKey ? label : field.key,
                        }),
                      },
                    ]
                  : undefined
              }
              extra={extra ?? hintLink}
            >
              {field.kind === "switch" ? (
                <Switch />
              ) : field.kind === "number" ? (
                <InputNumber
                  min={1}
                  max={50}
                  style={{ width: "100%" }}
                  placeholder={field.placeholder}
                />
              ) : (
                <Input
                  type={field.kind === "password" ? "password" : "text"}
                  placeholder={field.placeholder}
                  autoComplete="off"
                />
              )}
            </Form.Item>
          );
        })}
      </Form>
      {provider.configured ? (
        <Button
          danger
          icon={<Trash2 size={14} />}
          loading={revoking}
          onClick={handleRevoke}
        >
          {t("setupWizard.search.revoke")}
        </Button>
      ) : null}
    </Drawer>
  );
}

export default function SearchConfigPage() {
  const { t } = useTranslation();
  const [providers, setProviders] =
    useState<SearchProvider[]>(SEARCH_PROVIDERS);
  const [loading, setLoading] = useState(true);
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const loadedRef = useRef(false);
  const user = useCurrentUser();
  const canReuseModelKey = userCan(user, "providers") && userCan(user, "envs");

  const fetchEnvVars = useCallback(async () => {
    try {
      // Keep the page (and an open drawer) mounted on background refreshes.
      if (!loadedRef.current) setLoading(true);
      const envs = await envsApi.listEnvs();
      const envMap: Record<string, string> = {};
      envs.forEach((env) => {
        envMap[env.key] = env.value;
      });
      setEnvVars(envMap);
      setProviders(
        SEARCH_PROVIDERS.map((p) => ({
          ...p,
          configured: isProviderConfigured(p, envMap),
        })),
      );
    } catch (err) {
      console.error("Failed to load env vars:", err);
    } finally {
      loadedRef.current = true;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchEnvVars();
  }, [fetchEnvVars]);

  const editing = editingId
    ? providers.find((p) => p.id === editingId) ?? null
    : null;

  const sortedProviders = [...providers].sort((a, b) => {
    if (a.configured && !b.configured) return -1;
    if (!a.configured && b.configured) return 1;
    return 0;
  });

  const configuredProviders = providers.filter((p) => p.configured);
  const activeSource = configuredProviders[0];
  const configuredCount = configuredProviders.length;

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spin />
      </div>
    );
  }

  return (
    <>
      <p className={styles.intro}>{t("advancedSettings.search.desc")}</p>

      <div
        className={`${styles.status} ${activeSource ? styles.statusOk : ""}`}
      >
        <span className={styles.statusIcon} aria-hidden="true">
          {activeSource ? <CheckCircle size={18} /> : <Search size={18} />}
        </span>
        <div className={styles.statusBody}>
          <p className={styles.statusTitle}>
            {activeSource
              ? t(
                  "advancedSettings.search.sourceConfiguredTitle",
                  "当前搜索源：{{name}}",
                  { name: activeSource.name },
                )
              : t(
                  "advancedSettings.search.sourceBuiltinTitle",
                  "当前搜索源：内置搜索",
                )}
          </p>
          <p className={styles.statusDesc}>
            {activeSource
              ? t(
                  "advancedSettings.search.sourceConfiguredDesc",
                  "已配置第三方搜索服务，内置搜索默认不再加载，避免多个搜索工具同时暴露给模型。",
                )
              : t(
                  "advancedSettings.search.sourceBuiltinDesc",
                  "未配置第三方搜索服务时，仍可使用产品内置搜索服务；该服务无需 API Key，但不保证稳定性和可用性。配置第三方服务后会自动切换。",
                )}
          </p>
        </div>
      </div>

      <div className={styles.grid}>
        {sortedProviders.map((provider) => {
          const isActive = activeSource?.id === provider.id;
          const needsSetup = !provider.configured;
          const logo = searchProviderLogo(provider.id);
          const cardClass = [
            styles.card,
            isActive ? styles.cardActive : "",
            needsSetup ? styles.cardSetup : "",
          ]
            .filter(Boolean)
            .join(" ");

          return (
            <div
              key={provider.id}
              className={cardClass}
              role={needsSetup ? "button" : undefined}
              tabIndex={needsSetup ? 0 : undefined}
              onClick={needsSetup ? () => setEditingId(provider.id) : undefined}
              onKeyDown={
                needsSetup
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setEditingId(provider.id);
                      }
                    }
                  : undefined
              }
            >
              <div className={styles.cardHeader}>
                <div className={styles.logoTile}>
                  <img
                    src={logo}
                    alt={provider.name}
                    className={styles.logo}
                    draggable={false}
                  />
                </div>
                <div className={styles.titleBlock}>
                  <div className={styles.nameRow}>
                    <span className={styles.name}>{provider.name}</span>
                  </div>
                </div>
                <div className={styles.badges}>
                  {isActive ? (
                    <span className={`${styles.badge} ${styles.badgeActive}`}>
                      <Check size={11} />
                      {t("setupWizard.search.configured")}
                    </span>
                  ) : provider.configured ? (
                    <span className={`${styles.badge} ${styles.badgeOk}`}>
                      {t("setupWizard.search.configured")}
                    </span>
                  ) : (
                    <span className={`${styles.badge} ${styles.badgeSetup}`}>
                      {t("setupWizard.search.unconfigured")}
                    </span>
                  )}
                </div>
              </div>

              <p className={styles.description}>{t(provider.descriptionKey)}</p>

              <div className={styles.actions}>
                <Button
                  size="small"
                  type={needsSetup ? "primary" : "default"}
                  icon={<Settings2 size={14} />}
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingId(provider.id);
                  }}
                >
                  {needsSetup
                    ? t("advancedSettings.search.configure")
                    : t("common.edit")}
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <Text className={styles.footer}>
        {t("setupWizard.search.configuredCount", {
          count: configuredCount,
          total: providers.length,
        })}
      </Text>

      {editing ? (
        <ConfigureDrawer
          provider={editing}
          envVars={envVars}
          open
          canReuseModelKey={canReuseModelKey}
          onClose={() => setEditingId(null)}
          onSaved={() => void fetchEnvVars()}
        />
      ) : null}
    </>
  );
}

export { SearchConfigPage as SearchSettingsPanel };
