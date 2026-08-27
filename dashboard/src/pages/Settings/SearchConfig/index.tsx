import { useEffect, useState, useCallback } from "react";
import { App, Button, Form, Input, Typography, Spin, Modal } from "antd";

import {
  Check,
  CheckCircle,
  Search,
  Settings2,
  Trash2,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { envsApi } from "../../../api/modules/env";
import api from "../../../api";
import { customProviderLogo, getProviderLogo } from "../../../assets/providers";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

const { Text } = Typography;

interface SearchProvider {
  id: string;
  name: string;
  descriptionKey: string;
  docs_url?: string;
  required_keys: string[];
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
];

function searchProviderLogo(providerId: string): string {
  return getProviderLogo(providerId) ?? customProviderLogo;
}

interface ConfigureModalProps {
  provider: SearchProvider;
  envVars: Record<string, string>;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

function ConfigureModal({
  provider,
  envVars,
  open,
  onClose,
  onSaved,
}: ConfigureModalProps) {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    if (!open) return;
    const initialValues: Record<string, string> = {};
    provider.required_keys.forEach((key) => {
      if (envVars[key]) initialValues[key] = envVars[key];
    });
    form.setFieldsValue(initialValues);
  }, [envVars, provider.required_keys, form, open]);

  const handleSave = async () => {
    try {
      setSaving(true);
      const values = (await form.validateFields()) as Record<string, string>;
      const allEnvs = { ...envVars };
      provider.required_keys.forEach((key) => {
        if (values[key]) allEnvs[key] = values[key];
      });
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

  const handleTest = async () => {
    try {
      setTesting(true);
      const values = (await form.validateFields()) as Record<string, string>;
      const testEnvs = { ...envVars };
      provider.required_keys.forEach((key) => {
        if (values[key]) testEnvs[key] = values[key];
      });
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
          for (const key of provider.required_keys) {
            await envsApi.deleteEnv(key);
          }
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

  const modalTitle = provider.configured
    ? `${t("common.edit")} — ${provider.name}`
    : `${t("advancedSettings.search.configure")} — ${provider.name}`;

  return (
    <Modal
      title={modalTitle}
      open={open}
      onCancel={onClose}
      onOk={() => void handleSave()}
      confirmLoading={saving}
      okText={t("common.save")}
      cancelText={t("common.cancel")}
      destroyOnClose
      width={480}
    >
      <p className={styles.modalHint}>{t(provider.descriptionKey)}</p>
      <Form form={form} layout="vertical" requiredMark={false}>
        {provider.required_keys.map((key) => (
          <Form.Item
            key={key}
            name={key}
            label={key}
            rules={[
              {
                required: true,
                message: t("setupWizard.search.required", { key }),
              },
            ]}
            extra={
              key === "GOOGLE_CSE_ID" ? (
                <span>
                  {t("setupWizard.search.googleCseIdHint")}
                  {provider.docs_url ? (
                    <>
                      {" · "}
                      <a
                        href={provider.docs_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {t("setupWizard.search.getApiKey")}
                      </a>
                    </>
                  ) : null}
                </span>
              ) : undefined
            }
          >
            <Input.Password
              placeholder={t("setupWizard.search.required", { key })}
              autoComplete="off"
            />
          </Form.Item>
        ))}
      </Form>

      <div className={styles.modalActions}>
        <Button
          icon={<Zap size={14} />}
          loading={testing}
          onClick={() => void handleTest()}
        >
          {t("setupWizard.search.test")}
        </Button>
        {provider.docs_url ? (
          <Button
            type="link"
            onClick={() => window.open(provider.docs_url, "_blank")}
          >
            {t("setupWizard.search.docs")}
          </Button>
        ) : null}
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
      </div>
    </Modal>
  );
}

export default function SearchConfigPage() {
  const { t } = useTranslation();
  const [providers, setProviders] =
    useState<SearchProvider[]>(SEARCH_PROVIDERS);
  const [loading, setLoading] = useState(true);
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<SearchProvider | null>(null);

  const fetchEnvVars = useCallback(async () => {
    try {
      setLoading(true);
      const envs = await envsApi.listEnvs();
      const envMap: Record<string, string> = {};
      envs.forEach((env) => {
        envMap[env.key] = env.value;
      });
      setEnvVars(envMap);
      setProviders(
        SEARCH_PROVIDERS.map((p) => ({
          ...p,
          configured: p.required_keys.every((key) => !!envMap[key]),
        })),
      );
    } catch (err) {
      console.error("Failed to load env vars:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchEnvVars();
  }, [fetchEnvVars]);

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
      <TabPanelHeader
        icon={<Search size={22} />}
        title={t("nav.search")}
        description={t("advancedSettings.search.desc")}
      />

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
              onClick={needsSetup ? () => setEditing(provider) : undefined}
              onKeyDown={
                needsSetup
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setEditing(provider);
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
                    setEditing(provider);
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
        <ConfigureModal
          provider={editing}
          envVars={envVars}
          open
          onClose={() => setEditing(null)}
          onSaved={() => void fetchEnvVars()}
        />
      ) : null}
    </>
  );
}
