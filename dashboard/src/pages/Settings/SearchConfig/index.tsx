import { useEffect, useState, useCallback } from "react";
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  Typography,
  Spin,
  Switch,
  Tooltip,
} from "antd";

import {
  Activity,
  CheckCircle,
  Plus,
  Search,
  Pencil,
  Trash2,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { envsApi } from "../../../api/modules/env";
import {
  searchApi,
  type CustomSearchConfig,
  type CustomSearchProvider,
  type CustomSearchProviderUpdate,
} from "../../../api/modules/search";
import api from "../../../api";
import { customProviderLogo, getProviderLogo } from "../../../assets/providers";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import CustomSearchDrawer from "./CustomSearchDrawer";
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

interface ConfigureDrawerProps {
  provider: SearchProvider;
  envVars: Record<string, string>;
  open: boolean;
  onClose: () => void;
  onPersistSelection: (revoking: boolean) => Promise<void>;
  onRevoke: () => Promise<void>;
  onSaved: () => Promise<void>;
}

function ConfigureDrawer({
  provider,
  envVars,
  open,
  onClose,
  onPersistSelection,
  onRevoke,
  onSaved,
}: ConfigureDrawerProps) {
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
      await onPersistSelection(false);
      await envsApi.batchSaveEnvs(allEnvs);
      await onSaved();
      message.success(
        t("advancedSettings.search.custom.saveSuccess", {
          name: provider.name,
        }),
      );
      onClose();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        apiErrorMessage(err, t("setupWizard.search.saveFailed"), t),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleProbe = async () => {
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
          await onRevoke();
          message.success(
            t("setupWizard.search.revokeSuccess", { name: provider.name }),
          );
          onClose();
        } catch (err) {
          message.error(
            apiErrorMessage(err, t("setupWizard.search.revokeFailed"), t),
          );
        } finally {
          setRevoking(false);
        }
      },
    });
  };

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
              ) : provider.docs_url && key === provider.required_keys[0] ? (
                <a
                  href={provider.docs_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t("setupWizard.search.getApiKey")}
                </a>
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
  const { modal, message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<SearchProvider | null>(null);
  const [customConfig, setCustomConfig] = useState<CustomSearchConfig>({
    providers: [],
    active_provider_id: null,
  });
  const [customEditing, setCustomEditing] = useState<
    CustomSearchProvider | null | undefined
  >();
  const [updating, setUpdating] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      setLoadFailed(false);
      const [envs, custom] = await Promise.all([
        envsApi.listEnvs(),
        searchApi.getCustom(),
      ]);
      const envMap: Record<string, string> = {};
      envs.forEach((env) => {
        envMap[env.key] = env.value;
      });
      setEnvVars(envMap);
      setCustomConfig(custom);
    } catch (err) {
      setLoadFailed(true);
      message.error(
        apiErrorMessage(err, t("advancedSettings.search.custom.loadFailed"), t),
      );
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const savedProviders = customConfig.providers.map(
    ({ api_key_set: _apiKeySet, ...provider }) => provider,
  );

  const persistPresetSelection = async (
    provider: SearchProvider,
    revoking: boolean,
  ) => {
    setCustomConfig(
      await searchApi.saveCustom({
        providers: savedProviders,
        active_provider_id:
          revoking &&
          customConfig.active_provider_id === `preset:${provider.id}`
            ? null
            : customConfig.active_provider_id,
      }),
    );
  };

  const revokePresetProvider = async (provider: SearchProvider) => {
    await persistPresetSelection(provider, true);
    for (const key of provider.required_keys) {
      await envsApi.deleteEnv(key);
    }
    await fetchConfig();
  };

  const deletePresetProvider = (provider: SearchProvider) => {
    modal.confirm({
      title: t("setupWizard.search.revokeTitle", { name: provider.name }),
      content: t("setupWizard.search.revokeConfirm", { name: provider.name }),
      okText: t("setupWizard.search.revoke"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          setDeleting(`preset:${provider.id}`);
          await revokePresetProvider(provider);
          message.success(
            t("setupWizard.search.revokeSuccess", { name: provider.name }),
          );
        } catch (err) {
          message.error(
            apiErrorMessage(err, t("setupWizard.search.revokeFailed"), t),
          );
          throw err;
        } finally {
          setDeleting(null);
        }
      },
    });
  };

  const probeProvider = async (
    provider: SearchProvider | CustomSearchProvider,
  ) => {
    const isPreset = "required_keys" in provider;
    setTesting(isPreset ? `preset:${provider.id}` : provider.id);
    try {
      const result = isPreset
        ? await api.testSearch(provider.id, {}, true)
        : await searchApi.testCustom(
            (({ api_key_set: _apiKeySet, ...config }) => config)(provider),
          );
      if (result.success) {
        message.success(
          t("setupWizard.search.testSuccess", { name: provider.name }),
        );
      } else {
        message.error(
          t("setupWizard.search.testFailed", {
            name: provider.name,
            error:
              result.error ||
              result.error_type ||
              t("advancedSettings.search.custom.testError"),
          }),
        );
      }
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("advancedSettings.search.custom.testError"), t),
      );
    } finally {
      setTesting(null);
    }
  };

  const setActiveSource = async (id: string, enabled: boolean) => {
    if (updating) return;
    try {
      setUpdating(id);
      setCustomConfig(
        await searchApi.saveCustom({
          providers: savedProviders,
          active_provider_id: enabled ? id : null,
        }),
      );
      message.success(t("advancedSettings.search.custom.sourceSaved"));
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("setupWizard.search.saveFailed"), t),
      );
    } finally {
      setUpdating(null);
    }
  };

  const saveCustomProvider = async (provider: CustomSearchProviderUpdate) => {
    const isNew = !customConfig.providers.some((p) => p.id === provider.id);
    setCustomConfig(
      await searchApi.saveCustom({
        providers: isNew
          ? [...savedProviders, provider]
          : savedProviders.map((p) => (p.id === provider.id ? provider : p)),
        active_provider_id: customConfig.active_provider_id,
      }),
    );
    message.success(
      t("advancedSettings.search.custom.saveSuccess", { name: provider.name }),
    );
  };

  const deleteCustomProvider = (provider: CustomSearchProvider) => {
    modal.confirm({
      title: t("advancedSettings.search.custom.deleteTitle", {
        name: provider.name,
      }),
      content: t("advancedSettings.search.custom.deleteHint"),
      okText: t("common.delete"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          setCustomConfig(
            await searchApi.saveCustom({
              providers: savedProviders.filter((p) => p.id !== provider.id),
              active_provider_id:
                customConfig.active_provider_id === provider.id
                  ? null
                  : customConfig.active_provider_id,
            }),
          );
          message.success(t("advancedSettings.search.custom.deleted"));
        } catch (err) {
          message.error(
            apiErrorMessage(
              err,
              t("advancedSettings.search.custom.deleteFailed"),
              t,
            ),
          );
          throw err;
        }
      },
    });
  };

  const providers = SEARCH_PROVIDERS.map((p) => ({
    ...p,
    configured:
      !!customConfig.configured_preset_ids?.includes(p.id) ||
      p.required_keys.every((key) => !!envVars[key]?.trim()),
  }));
  const sortedProviders = [...providers].sort((a, b) => {
    if (a.configured && !b.configured) return -1;
    if (!a.configured && b.configured) return 1;
    return 0;
  });

  const configuredProviders = providers.filter((p) => p.configured);
  const activeSource =
    customConfig.providers.find(
      (p) => p.id === customConfig.active_provider_id,
    ) ??
    providers.find((p) => `preset:${p.id}` === customConfig.active_provider_id);
  const configuredCount =
    configuredProviders.length + customConfig.providers.length;

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spin />
      </div>
    );
  }

  if (loadFailed) {
    return (
      <div className={styles.loading}>
        <Button onClick={() => void fetchConfig()}>{t("common.retry")}</Button>
      </div>
    );
  }

  return (
    <>
      <TabPanelHeader
        icon={<Search size={22} />}
        title={t("models.searchModelsTab")}
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
              ? t("advancedSettings.search.sourceConfiguredTitle", {
                  name: activeSource.name,
                })
              : t("advancedSettings.search.sourceBuiltinTitle")}
          </p>
          <p className={styles.statusDesc}>
            {t(
              activeSource
                ? "advancedSettings.search.sourceConfiguredDesc"
                : "advancedSettings.search.sourceBuiltinDesc",
            )}
          </p>
        </div>
      </div>

      <div className={styles.toolbar}>
        <Button
          type="primary"
          icon={<Plus size={14} />}
          onClick={() => setCustomEditing(null)}
          disabled={!!updating}
        >
          {t("advancedSettings.search.custom.add")}
        </Button>
      </div>

      <div className={styles.grid}>
        {customConfig.providers.map((provider) => {
          const isActive = customConfig.active_provider_id === provider.id;
          return (
            <div
              key={provider.id}
              role="article"
              aria-label={provider.name}
              className={`${styles.card} ${isActive ? styles.cardActive : ""}`}
            >
              <div className={styles.cardHeader}>
                <div className={styles.logoTile}>
                  <img
                    src={customProviderLogo}
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
                <span className={`${styles.badge} ${styles.badgeOk}`}>
                  {t("advancedSettings.search.custom.label")}
                </span>
              </div>
              <p className={styles.description}>{provider.url}</p>
              <div className={styles.actions}>
                <div
                  className={styles.enableControl}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Switch
                    size="small"
                    aria-label={provider.name}
                    checked={isActive}
                    loading={updating === provider.id}
                    disabled={!!updating || !!deleting}
                    onChange={(enabled) =>
                      void setActiveSource(provider.id, enabled)
                    }
                  />
                  <span className={styles.enableStatus}>
                    {t(`common.${isActive ? "enabled" : "disabled"}`)}
                  </span>
                </div>
                <div
                  className={styles.actionButtons}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Tooltip title={t("advancedSettings.search.probe")}>
                    <Button
                      type="text"
                      size="small"
                      className={styles.actionButton}
                      aria-label={t("advancedSettings.search.probe")}
                      icon={<Zap size={14} />}
                      loading={testing === provider.id}
                      disabled={!!testing || !!updating || !!deleting}
                      onClick={() => void probeProvider(provider)}
                    />
                  </Tooltip>
                  <Tooltip title={t("common.edit")}>
                    <Button
                      type="text"
                      size="small"
                      className={styles.actionButton}
                      aria-label={t("common.edit")}
                      icon={<Pencil size={14} />}
                      disabled={!!updating || !!deleting}
                      onClick={() => setCustomEditing(provider)}
                    />
                  </Tooltip>
                  <Tooltip title={t("common.delete")}>
                    <Button
                      type="text"
                      size="small"
                      danger
                      className={styles.actionButton}
                      aria-label={t("common.delete")}
                      icon={<Trash2 size={14} />}
                      disabled={!!updating || !!deleting}
                      onClick={() => deleteCustomProvider(provider)}
                    />
                  </Tooltip>
                </div>
              </div>
            </div>
          );
        })}
        {sortedProviders.map((provider) => {
          const sourceId = `preset:${provider.id}`;
          const isActive = customConfig.active_provider_id === sourceId;
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
              role={needsSetup ? "button" : "article"}
              aria-label={provider.name}
              tabIndex={needsSetup ? 0 : undefined}
              onClick={needsSetup ? () => setEditing(provider) : undefined}
              onKeyDown={
                needsSetup
                  ? (e) => {
                      if (e.target !== e.currentTarget) return;
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
                  {provider.configured ? (
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
                <div
                  className={styles.enableControl}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Tooltip
                    title={
                      needsSetup
                        ? t("advancedSettings.search.custom.configureFirst")
                        : undefined
                    }
                  >
                    <Switch
                      size="small"
                      aria-label={provider.name}
                      checked={isActive}
                      loading={updating === sourceId}
                      disabled={
                        (!isActive && needsSetup) || !!updating || !!deleting
                      }
                      onClick={(_, event) => event.stopPropagation()}
                      onChange={(enabled) =>
                        void setActiveSource(sourceId, enabled)
                      }
                    />
                  </Tooltip>
                  <span className={styles.enableStatus}>
                    {t(`common.${isActive ? "enabled" : "disabled"}`)}
                  </span>
                </div>
                <div
                  className={styles.actionButtons}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Tooltip title={t("advancedSettings.search.probe")}>
                    <Button
                      type="text"
                      size="small"
                      className={styles.actionButton}
                      aria-label={t("advancedSettings.search.probe")}
                      icon={<Zap size={14} />}
                      loading={testing === sourceId}
                      disabled={
                        needsSetup || !!testing || !!updating || !!deleting
                      }
                      onClick={(e) => {
                        e.stopPropagation();
                        void probeProvider(provider);
                      }}
                    />
                  </Tooltip>
                  <Tooltip
                    title={
                      needsSetup
                        ? t("advancedSettings.search.configure")
                        : t("common.edit")
                    }
                  >
                    <Button
                      type="text"
                      size="small"
                      className={styles.actionButton}
                      aria-label={
                        needsSetup
                          ? t("advancedSettings.search.configure")
                          : t("common.edit")
                      }
                      icon={<Pencil size={14} />}
                      disabled={!!updating || !!deleting}
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditing(provider);
                      }}
                    />
                  </Tooltip>
                  <Tooltip title={t("common.delete")}>
                    <Button
                      type="text"
                      size="small"
                      danger
                      className={styles.actionButton}
                      aria-label={t("common.delete")}
                      icon={<Trash2 size={14} />}
                      loading={deleting === sourceId}
                      disabled={
                        !provider.required_keys.some((key) => key in envVars) ||
                        !!updating ||
                        !!deleting
                      }
                      onClick={(e) => {
                        e.stopPropagation();
                        deletePresetProvider(provider);
                      }}
                    />
                  </Tooltip>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <Text className={styles.footer}>
        {t("setupWizard.search.configuredCount", {
          count: configuredCount,
          total: providers.length + customConfig.providers.length,
        })}
      </Text>

      {editing ? (
        <ConfigureDrawer
          provider={editing}
          envVars={envVars}
          open
          onClose={() => setEditing(null)}
          onPersistSelection={(revoking) =>
            persistPresetSelection(editing, revoking)
          }
          onRevoke={() => revokePresetProvider(editing)}
          onSaved={fetchConfig}
        />
      ) : null}
      {customEditing !== undefined ? (
        <CustomSearchDrawer
          provider={customEditing}
          onClose={() => setCustomEditing(undefined)}
          onSave={saveCustomProvider}
        />
      ) : null}
    </>
  );
}

export { SearchConfigPage as SearchSettingsPanel };
