import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  AutoComplete,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  CheckCircle2,
  Images,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  Video,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  mediaGenerationApi,
  type MediaGenerationSettings,
  type MediaProviderInput,
  type MediaProviderName,
  type MediaProviderPreset,
  type MediaProviderSettings,
} from "../../../api/modules/mediaGeneration";
import { customProviderLogo, getProviderLogo } from "../../../assets/providers";
import { message } from "@/utils/antdMessage";
import styles from "./index.module.less";

const { Text } = Typography;

interface MediaProviderDraft extends MediaProviderSettings {
  api_key: string;
}

interface MediaGenerationDraft
  extends Omit<MediaGenerationSettings, "providers"> {
  providers: MediaProviderDraft[];
}

type ProviderModalMode = "create" | "edit";

interface ProviderFormValues {
  provider: MediaProviderName;
  display_name: string;
  base_url: string;
  api_key: string;
  image_enabled: boolean;
  video_enabled: boolean;
  image_model: string;
  video_model: string;
}

function nextProviderId(
  provider: MediaProviderName,
  providers: MediaProviderDraft[],
): string {
  const ids = new Set(providers.map((item) => item.id));
  const base = `${provider}-default`;
  if (!ids.has(base)) return base;
  let suffix = 2;
  while (ids.has(`${provider}-${suffix}`)) suffix += 1;
  return `${provider}-${suffix}`;
}

function providerInput(provider: MediaProviderDraft): MediaProviderInput {
  return {
    id: provider.id,
    provider: provider.provider,
    display_name: provider.display_name,
    enabled: provider.enabled,
    base_url: provider.base_url,
    image_enabled: provider.image_enabled,
    video_enabled: provider.video_enabled,
    image_model: provider.image_model,
    video_model: provider.video_model,
    api_key: provider.api_key.trim() || null,
  };
}

function draftSettings(
  settings: MediaGenerationSettings,
): MediaGenerationDraft {
  return {
    ...settings,
    providers: settings.providers.map((provider) => ({
      ...provider,
      api_key: "",
    })),
  };
}

function hasCredential(provider: MediaProviderDraft): boolean {
  return provider.api_key_set || Boolean(provider.api_key.trim());
}

function normalizeRoutes(
  providers: MediaProviderDraft[],
  imageRoute: string | null,
  videoRoute: string | null,
): Pick<
  MediaGenerationDraft,
  "default_image_provider" | "default_video_provider"
> {
  const imageProviders = providers.filter(
    (item) => item.enabled && item.image_enabled && hasCredential(item),
  );
  const videoProviders = providers.filter(
    (item) => item.enabled && item.video_enabled && hasCredential(item),
  );
  return {
    default_image_provider: imageProviders.some(
      (item) => item.id === imageRoute,
    )
      ? imageRoute
      : imageProviders[0]?.id ?? null,
    default_video_provider: videoProviders.some(
      (item) => item.id === videoRoute,
    )
      ? videoRoute
      : videoProviders[0]?.id ?? null,
  };
}

function providerLogo(provider: MediaProviderName): string {
  return getProviderLogo(provider) ?? customProviderLogo;
}

export function MediaGenerationSettingsPanel() {
  const { t } = useTranslation();
  const { modal } = App.useApp();
  const [form] = Form.useForm<ProviderFormValues>();
  const [config, setConfig] = useState<MediaGenerationDraft | null>(null);
  const [presets, setPresets] = useState<MediaProviderPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);
  const [providerModalOpen, setProviderModalOpen] = useState(false);
  const [providerModalMode, setProviderModalMode] =
    useState<ProviderModalMode>("create");
  const [editingProvider, setEditingProvider] =
    useState<MediaProviderDraft | null>(null);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const [settings, providerPresets] = await Promise.all([
        mediaGenerationApi.get(),
        mediaGenerationApi.getPresets(),
      ]);
      setConfig(draftSettings(settings));
      setPresets(providerPresets);
    } catch (err) {
      message.error(t("mediaGeneration.loadError"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const presetMap = useMemo(
    () => new Map(presets.map((preset) => [preset.provider, preset])),
    [presets],
  );

  const persist = useCallback(
    async (next: MediaGenerationDraft): Promise<boolean> => {
      setSaving(true);
      try {
        const saved = await mediaGenerationApi.save({
          enabled: next.enabled,
          providers: next.providers.map(providerInput),
          default_image_provider: next.default_image_provider,
          default_video_provider: next.default_video_provider,
        });
        setConfig(draftSettings(saved));
        message.success(t("mediaGeneration.saved"));
        return true;
      } catch (err) {
        message.error(
          err instanceof Error ? err.message : t("mediaGeneration.saveFailed"),
        );
        return false;
      } finally {
        setSaving(false);
      }
    },
    [t],
  );

  const makeProvider = useCallback(
    (providerName: MediaProviderName): MediaProviderDraft | null => {
      if (!config) return null;
      const preset = presetMap.get(providerName);
      if (!preset) return null;
      return {
        id: nextProviderId(providerName, config.providers),
        provider: providerName,
        display_name: preset.display_name,
        enabled: true,
        base_url: preset.base_url,
        image_enabled: true,
        video_enabled: true,
        image_model: preset.image_models[0] || "",
        video_model: preset.video_models[0] || "",
        api_key_set: false,
        configured: false,
        api_key: "",
      };
    },
    [config, presetMap],
  );

  const openProviderModal = (
    mode: ProviderModalMode,
    provider: MediaProviderDraft,
  ) => {
    setProviderModalMode(mode);
    setEditingProvider(provider);
    form.setFieldsValue({
      provider: provider.provider,
      display_name: provider.display_name,
      base_url: provider.base_url,
      api_key: "",
      image_enabled: provider.image_enabled,
      video_enabled: provider.video_enabled,
      image_model: provider.image_model,
      video_model: provider.video_model,
    });
    setProviderModalOpen(true);
  };

  const openCreateModal = (providerName: MediaProviderName = "volcengine") => {
    const provider = makeProvider(providerName);
    if (provider) openProviderModal("create", provider);
  };

  const handleProviderTypeChange = (providerName: MediaProviderName) => {
    const next = makeProvider(providerName);
    if (!next) return;
    setEditingProvider(next);
    form.setFieldsValue({
      provider: next.provider,
      display_name: next.display_name,
      base_url: next.base_url,
      image_enabled: next.image_enabled,
      video_enabled: next.video_enabled,
      image_model: next.image_model,
      video_model: next.video_model,
    });
  };

  const providerFromForm = async (): Promise<MediaProviderDraft | null> => {
    if (!editingProvider) return null;
    try {
      const values = await form.validateFields();
      return {
        ...editingProvider,
        ...values,
        display_name: values.display_name.trim(),
        base_url: values.base_url.trim(),
        image_model: values.image_model.trim(),
        video_model: values.video_model.trim(),
        api_key: values.api_key.trim(),
      };
    } catch {
      return null;
    }
  };

  const handleSaveProvider = async () => {
    if (!config) return;
    const provider = await providerFromForm();
    if (!provider) return;
    const providers =
      providerModalMode === "create"
        ? [...config.providers, provider]
        : config.providers.map((item) =>
            item.id === provider.id ? provider : item,
          );
    const routes = normalizeRoutes(
      providers,
      config.default_image_provider,
      config.default_video_provider,
    );
    if (await persist({ ...config, providers, ...routes })) {
      setProviderModalOpen(false);
    }
  };

  const handleTest = async (
    provider: MediaProviderDraft,
    kind: "credentials" | "image" | "video",
  ) => {
    const testId = `${provider.id}:${kind}`;
    setTesting(testId);
    try {
      const result = await mediaGenerationApi.test({
        kind,
        provider: providerInput(provider),
      });
      if (!result.ok) {
        message.error(result.error || t("mediaGeneration.testFailed"));
        return;
      }
      message.success(
        t(
          kind === "credentials"
            ? "mediaGeneration.testSuccess"
            : kind === "image"
            ? "mediaGeneration.imageTestSuccess"
            : "mediaGeneration.videoTestSuccess",
        ),
      );
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("mediaGeneration.testFailed"),
      );
    } finally {
      setTesting(null);
    }
  };

  const handleModalTest = async (kind: "credentials" | "image" | "video") => {
    const provider = await providerFromForm();
    if (provider) await handleTest(provider, kind);
  };

  const handleToggleProvider = async (providerId: string, enabled: boolean) => {
    if (!config) return;
    const providers = config.providers.map((item) =>
      item.id === providerId ? { ...item, enabled } : item,
    );
    const routes = normalizeRoutes(
      providers,
      config.default_image_provider,
      config.default_video_provider,
    );
    await persist({ ...config, providers, ...routes });
  };

  const handleDeleteProvider = (provider: MediaProviderDraft) => {
    if (!config) return;
    modal.confirm({
      title: t("mediaGeneration.deleteProviderTitle"),
      content: t("mediaGeneration.deleteProviderConfirm", {
        name: provider.display_name,
      }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        const providers = config.providers.filter(
          (item) => item.id !== provider.id,
        );
        const routes = normalizeRoutes(
          providers,
          config.default_image_provider,
          config.default_video_provider,
        );
        await persist({ ...config, providers, ...routes });
      },
    });
  };

  const configuredTypes = new Set(
    config?.providers.map((provider) => provider.provider) ?? [],
  );
  const unconfiguredPresets = presets.filter(
    (preset) => !configuredTypes.has(preset.provider),
  );
  const imageRoutes =
    config?.providers
      .filter((provider) => provider.enabled && provider.image_enabled)
      .map((provider) => ({
        value: provider.id,
        label: `${provider.display_name} · ${provider.image_model}`,
      })) ?? [];
  const videoRoutes =
    config?.providers
      .filter((provider) => provider.enabled && provider.video_enabled)
      .map((provider) => ({
        value: provider.id,
        label: `${provider.display_name} · ${provider.video_model}`,
      })) ?? [];

  const modalPreset = editingProvider
    ? presetMap.get(editingProvider.provider)
    : undefined;
  const watchedApiKey = Form.useWatch("api_key", form) ?? "";
  const modalHasKey = editingProvider
    ? editingProvider.api_key_set || Boolean(watchedApiKey.trim())
    : false;
  const modalImageEnabled = Form.useWatch("image_enabled", form) ?? true;
  const modalVideoEnabled = Form.useWatch("video_enabled", form) ?? true;

  if (loading || !config) {
    return <Text type="secondary">{t("mediaGeneration.loading")}</Text>;
  }

  return (
    <>
      <Card className={styles.routePanel}>
        <div className={styles.routeHeader}>
          <div className={styles.routeHeading}>
            <span className={styles.routeIcon}>
              <Images size={19} />
            </span>
            <div>
              <h2 className={styles.routeTitle}>
                {t("mediaGeneration.routingTitle")}
              </h2>
              <p className={styles.routeDescription}>
                {t("mediaGeneration.routingDescription")}
              </p>
            </div>
          </div>
          <label className={styles.globalToggle}>
            <Switch
              size="small"
              checked={config.enabled}
              onChange={(enabled) => setConfig({ ...config, enabled })}
            />
            <span>{t("mediaGeneration.enable")}</span>
          </label>
        </div>

        <div className={styles.routeGrid}>
          <div className={styles.routeField}>
            <div className={styles.routeFieldLabel}>
              <Images size={14} />
              <span>{t("mediaGeneration.defaultImageRoute")}</span>
            </div>
            <Select
              allowClear
              style={{ width: "100%" }}
              value={config.default_image_provider}
              options={imageRoutes}
              placeholder={t("mediaGeneration.selectDefaultImageRoute")}
              onChange={(value) =>
                setConfig({
                  ...config,
                  default_image_provider: value || null,
                })
              }
            />
          </div>
          <div className={styles.routeField}>
            <div className={styles.routeFieldLabel}>
              <Video size={14} />
              <span>{t("mediaGeneration.defaultVideoRoute")}</span>
            </div>
            <Select
              allowClear
              style={{ width: "100%" }}
              value={config.default_video_provider}
              options={videoRoutes}
              placeholder={t("mediaGeneration.selectDefaultVideoRoute")}
              onChange={(value) =>
                setConfig({
                  ...config,
                  default_video_provider: value || null,
                })
              }
            />
          </div>
        </div>

        <div className={styles.routeFooter}>
          <Button
            icon={<RefreshCw size={14} />}
            onClick={() => void fetchConfig()}
          >
            {t("common.refresh")}
          </Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void persist(config)}
          >
            {t("mediaGeneration.saveRouting")}
          </Button>
        </div>
      </Card>

      <div className={styles.providerSectionHeader}>
        <div>
          <h2 className={styles.providerSectionTitle}>
            {t("mediaGeneration.providerSectionTitle")}
          </h2>
          <p className={styles.providerSectionDescription}>
            {t("mediaGeneration.providerSectionDescription")}
          </p>
        </div>
        <Button icon={<Plus size={14} />} onClick={() => openCreateModal()}>
          {t("mediaGeneration.addProvider")}
        </Button>
      </div>

      {config.providers.length === 0 && unconfiguredPresets.length === 0 ? (
        <Empty description={t("mediaGeneration.noProviders")} />
      ) : (
        <div className={styles.providerGrid}>
          {config.providers.map((provider) => {
            const statusReady = provider.api_key_set;
            const logo = providerLogo(provider.provider);
            const isHover = hoveredCard === provider.id;
            return (
              <Card
                key={provider.id}
                hoverable
                onMouseEnter={() => setHoveredCard(provider.id)}
                onMouseLeave={() => setHoveredCard(null)}
                onClick={() => openProviderModal("edit", provider)}
                className={`${styles.providerCard} ${
                  isHover ? styles.providerCardHover : ""
                } ${statusReady ? styles.configuredCard : ""} ${
                  provider.enabled ? "" : styles.disabledCard
                }`}
              >
                <div className={styles.cardMain}>
                  <div className={styles.cardHeader}>
                    <div className={styles.providerIdentity}>
                      <img
                        src={logo}
                        alt={provider.display_name}
                        className={styles.providerLogo}
                      />
                      <div className={styles.providerNameBlock}>
                        <span
                          className={styles.providerName}
                          title={provider.display_name}
                        >
                          {provider.display_name}
                        </span>
                        <span className={styles.providerType}>
                          {provider.provider}
                        </span>
                      </div>
                    </div>
                    <div
                      className={`${styles.status} ${
                        statusReady ? styles.statusReady : ""
                      }`}
                    >
                      <span className={styles.statusDot} />
                      <span>
                        {t(
                          statusReady
                            ? "mediaGeneration.authorized"
                            : "mediaGeneration.unauthorized",
                        )}
                      </span>
                    </div>
                  </div>

                  <div className={styles.detailList}>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Base URL</span>
                      <span
                        className={styles.detailValue}
                        title={provider.base_url}
                      >
                        {provider.base_url}
                      </span>
                    </div>
                    {provider.image_enabled && (
                      <div className={styles.detailRow}>
                        <span className={styles.detailLabel}>
                          <Images size={13} />
                          {t("mediaGeneration.image")}
                        </span>
                        <span
                          className={styles.detailValue}
                          title={provider.image_model}
                        >
                          {provider.image_model}
                        </span>
                      </div>
                    )}
                    {provider.video_enabled && (
                      <div className={styles.detailRow}>
                        <span className={styles.detailLabel}>
                          <Video size={13} />
                          {t("mediaGeneration.video")}
                        </span>
                        <span
                          className={styles.detailValue}
                          title={provider.video_model}
                        >
                          {provider.video_model}
                        </span>
                      </div>
                    )}
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>
                        {t("mediaGeneration.routeId")}
                      </span>
                      <span className={styles.detailValue} title={provider.id}>
                        {provider.id}
                      </span>
                    </div>
                  </div>
                </div>

                <div className={styles.cardFooter}>
                  <div className={styles.cardFooterLeft}>
                    <Switch
                      size="small"
                      checked={provider.enabled}
                      loading={saving}
                      onClick={(_, event) => event.stopPropagation()}
                      onChange={(enabled) =>
                        void handleToggleProvider(provider.id, enabled)
                      }
                    />
                    <span>
                      {t(
                        provider.enabled
                          ? "mediaGeneration.enabledStatus"
                          : "mediaGeneration.disabledStatus",
                      )}
                    </span>
                  </div>
                  <div className={styles.cardFooterActions}>
                    <Tooltip title={t("mediaGeneration.testCredentials")}>
                      <Button
                        type="text"
                        size="small"
                        className={styles.iconButton}
                        icon={<Zap size={14} />}
                        loading={testing === `${provider.id}:credentials`}
                        disabled={!statusReady}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleTest(provider, "credentials");
                        }}
                      />
                    </Tooltip>
                    <Tooltip title={t("mediaGeneration.editProvider")}>
                      <Button
                        type="text"
                        size="small"
                        className={styles.iconButton}
                        icon={<Pencil size={14} />}
                        onClick={(event) => {
                          event.stopPropagation();
                          openProviderModal("edit", provider);
                        }}
                      />
                    </Tooltip>
                    <Tooltip title={t("common.delete")}>
                      <Button
                        danger
                        type="text"
                        size="small"
                        className={styles.iconButton}
                        icon={<Trash2 size={14} />}
                        onClick={(event) => {
                          event.stopPropagation();
                          handleDeleteProvider(provider);
                        }}
                      />
                    </Tooltip>
                  </div>
                </div>
              </Card>
            );
          })}

          {unconfiguredPresets.map((preset) => {
            const cardId = `preset-${preset.provider}`;
            const isHover = hoveredCard === cardId;
            return (
              <Card
                key={cardId}
                hoverable
                onMouseEnter={() => setHoveredCard(cardId)}
                onMouseLeave={() => setHoveredCard(null)}
                onClick={() => openCreateModal(preset.provider)}
                className={`${styles.providerCard} ${styles.presetCard} ${
                  isHover ? styles.providerCardHover : ""
                }`}
              >
                <div className={styles.cardMain}>
                  <div className={styles.cardHeader}>
                    <div className={styles.providerIdentity}>
                      <img
                        src={providerLogo(preset.provider)}
                        alt={preset.display_name}
                        className={styles.providerLogo}
                      />
                      <div className={styles.providerNameBlock}>
                        <span
                          className={styles.providerName}
                          title={preset.display_name}
                        >
                          {preset.display_name}
                        </span>
                        <span className={styles.providerType}>
                          {preset.provider}
                        </span>
                      </div>
                    </div>
                    <div className={styles.status}>
                      <span className={styles.statusDot} />
                      <span>{t("mediaGeneration.notConfigured")}</span>
                    </div>
                  </div>
                  <div className={styles.detailList}>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Base URL</span>
                      <span
                        className={styles.detailValue}
                        title={preset.base_url}
                      >
                        {preset.base_url}
                      </span>
                    </div>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>
                        <Images size={13} />
                        {t("mediaGeneration.image")}
                      </span>
                      <span
                        className={styles.detailValue}
                        title={preset.image_models[0]}
                      >
                        {preset.image_models[0]}
                      </span>
                    </div>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>
                        <Video size={13} />
                        {t("mediaGeneration.video")}
                      </span>
                      <span
                        className={styles.detailValue}
                        title={preset.video_models[0]}
                      >
                        {preset.video_models[0]}
                      </span>
                    </div>
                  </div>
                </div>
                <div className={styles.cardFooter}>
                  <div className={styles.cardFooterLeft}>
                    <Tag bordered={false}>{t("mediaGeneration.preset")}</Tag>
                  </div>
                  <div className={styles.cardFooterActions}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t("mediaGeneration.setupProvider")}
                    </Text>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        title={t(
          providerModalMode === "create"
            ? "mediaGeneration.addProvider"
            : "mediaGeneration.editProvider",
        )}
        open={providerModalOpen}
        onCancel={() => setProviderModalOpen(false)}
        width={640}
        footer={
          <div className={styles.modalFooter}>
            <Button onClick={() => setProviderModalOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              type="primary"
              loading={saving}
              onClick={() => void handleSaveProvider()}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        <Form form={form} layout="vertical" requiredMark={false}>
          {providerModalMode === "create" && (
            <Form.Item
              name="provider"
              label={t("mediaGeneration.providerType")}
              rules={[{ required: true }]}
            >
              <Select
                options={presets.map((preset) => ({
                  value: preset.provider,
                  label: preset.display_name,
                }))}
                onChange={handleProviderTypeChange}
              />
            </Form.Item>
          )}

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: "0 16px",
            }}
          >
            <Form.Item label={t("mediaGeneration.instanceId")}>
              <Input value={editingProvider?.id} disabled />
            </Form.Item>
            <Form.Item
              name="display_name"
              label={t("mediaGeneration.displayName")}
              rules={[{ required: true, whitespace: true }]}
            >
              <Input />
            </Form.Item>
          </div>

          <Form.Item
            name="base_url"
            label={t("mediaGeneration.baseUrl")}
            rules={[{ required: true, type: "url" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="api_key"
            label={t("mediaGeneration.apiKey")}
            extra={
              editingProvider?.api_key_set ? (
                <Text type="secondary">
                  <CheckCircle2 size={12} style={{ marginRight: 4 }} />
                  {t("mediaGeneration.apiKeySet")}
                </Text>
              ) : null
            }
            rules={[
              {
                validator: async (_, value: string) => {
                  if (editingProvider?.api_key_set || value?.trim()) return;
                  throw new Error(t("mediaGeneration.apiKeyRequired"));
                },
              },
            ]}
          >
            <Input.Password
              autoComplete="new-password"
              placeholder={
                editingProvider?.api_key_set
                  ? t("mediaGeneration.apiKeyKeepPlaceholder")
                  : t("mediaGeneration.apiKeyPlaceholder")
              }
            />
          </Form.Item>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: 16,
            }}
          >
            <Card size="small">
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <Text strong>{t("mediaGeneration.enableImage")}</Text>
                <Form.Item name="image_enabled" valuePropName="checked" noStyle>
                  <Switch size="small" />
                </Form.Item>
              </Space>
              {modalImageEnabled && (
                <Form.Item
                  name="image_model"
                  label={t("mediaGeneration.imageModel")}
                  style={{ marginTop: 12, marginBottom: 0 }}
                  rules={[{ required: true, whitespace: true }]}
                >
                  <AutoComplete
                    options={(modalPreset?.image_models ?? []).map((model) => ({
                      value: model,
                    }))}
                    placeholder={t("mediaGeneration.customModelPlaceholder")}
                  />
                </Form.Item>
              )}
            </Card>

            <Card size="small">
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <Text strong>{t("mediaGeneration.enableVideo")}</Text>
                <Form.Item name="video_enabled" valuePropName="checked" noStyle>
                  <Switch size="small" />
                </Form.Item>
              </Space>
              {modalVideoEnabled && (
                <Form.Item
                  name="video_model"
                  label={t("mediaGeneration.videoModel")}
                  style={{ marginTop: 12, marginBottom: 0 }}
                  rules={[{ required: true, whitespace: true }]}
                >
                  <AutoComplete
                    options={(modalPreset?.video_models ?? []).map((model) => ({
                      value: model,
                    }))}
                    placeholder={t("mediaGeneration.customModelPlaceholder")}
                  />
                </Form.Item>
              )}
            </Card>
          </div>

          <div className={styles.testActions}>
            <Button
              icon={<Zap size={14} />}
              loading={
                editingProvider != null &&
                testing === `${editingProvider.id}:credentials`
              }
              disabled={!modalHasKey}
              onClick={() => void handleModalTest("credentials")}
            >
              {t("mediaGeneration.testCredentials")}
            </Button>
            {modalImageEnabled && (
              <Button
                loading={
                  editingProvider != null &&
                  testing === `${editingProvider.id}:image`
                }
                disabled={!modalHasKey}
                onClick={() => void handleModalTest("image")}
              >
                {t("mediaGeneration.testImageModel")}
              </Button>
            )}
            {modalVideoEnabled && (
              <Button
                loading={
                  editingProvider != null &&
                  testing === `${editingProvider.id}:video`
                }
                disabled={!modalHasKey}
                onClick={() => void handleModalTest("video")}
              >
                {t("mediaGeneration.testVideoModel")}
              </Button>
            )}
          </div>

          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message={t("mediaGeneration.modelTestBillingHint")}
          />
        </Form>
      </Modal>
    </>
  );
}

export default MediaGenerationSettingsPanel;
