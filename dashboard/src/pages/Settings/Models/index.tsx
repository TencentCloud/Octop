/**
 * Models — admin-only provider management page.
 *
 * Admins can create, edit, enable/disable, test, and delete providers.
 * All providers are globally available to every agent.
 *
 * Layout:
 *  1. Preset providers (from /providers/presets) — shows configured ones via
 *     ProviderCard, unconfigured ones as "click to set up" cards.
 *  2. Custom providers — any configured provider whose name doesn't match a preset.
 */
import { useMemo, useState } from "react";
import { Button, Divider, Empty, Space, Tabs, Typography } from "antd";
import { Images, MessageSquareText, Plus, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import PageShell from "../../../layouts/PageShell";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { userCan } from "../../../utils/permissions";
import { useProviders, type ProviderRow } from "./useProviders";
import { groupPresets, isLocalPreset, isPresetProvider } from "./presetUtils";
import type { PresetGroup } from "./presetUtils";
import type { ProviderPreset } from "./useProviders";
import {
  CustomProviderModal,
  ActiveModelPool,
  LoadingState,
  PresetGroupCard,
  PresetProviderCard,
  ProviderCard,
} from "./components";
import styles from "./index.module.less";
import { MediaGenerationSettingsPanel } from "../MediaGeneration";

const { Title } = Typography;

export default function ModelsPage() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const canProviders = userCan(user, "providers");
  const canOllama = userCan(user, "ollama_models");
  const canOnnx = userCan(user, "onnx_models");
  const {
    providers,
    presets,
    resolvedModels,
    activeModel,
    modelReasoning,
    loading,
    error,
    fetchAll,
  } = useProviders();
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const modelCategory =
    canProviders && searchParams.get("tab") === "generation"
      ? "generation"
      : "chat";
  const setModelCategory = (next: string) => {
    const updated = new URLSearchParams(searchParams);
    if (next === "generation") updated.set("tab", "generation");
    else updated.delete("tab");
    setSearchParams(updated, { replace: true });
  };

  const cloudPresets = useMemo(
    () => groupPresets(presets.filter((p) => !isLocalPreset(p))),
    [presets],
  );
  const localPresets = useMemo(
    () =>
      groupPresets(
        presets.filter((p) => {
          if (!isLocalPreset(p)) return false;
          if (p.id === "onnx") return canOnnx;
          if (p.id === "ollama") return canOllama;
          return canOllama || canOnnx;
        }),
      ),
    [presets, canOllama, canOnnx],
  );
  const showCloudTab = canProviders;
  const showLocalTab =
    (canOllama || canOnnx) &&
    (localPresets.grouped.length > 0 || localPresets.ungrouped.length > 0);
  const showPresetSection = showCloudTab || showLocalTab;

  const renderPresetGrid = (
    grouped: PresetGroup[],
    singles: ProviderPreset[],
  ) => {
    if (grouped.length === 0 && singles.length === 0) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("models.noPresetProvidersInTab")}
        />
      );
    }
    return (
      <div className={styles.providerCards}>
        {grouped.map((group) => (
          <PresetGroupCard
            key={group.groupKey}
            group={group}
            providers={providers}
            onSaved={fetchAll}
            isHover={hoveredCard === `group-${group.groupKey}`}
            onMouseEnter={() => setHoveredCard(`group-${group.groupKey}`)}
            onMouseLeave={() => setHoveredCard(null)}
          />
        ))}
        {singles.map((preset) => (
          <PresetProviderCard
            key={preset.id}
            preset={preset}
            providers={providers}
            onSaved={fetchAll}
            isHover={hoveredCard === `preset-${preset.id}`}
            onMouseEnter={() => setHoveredCard(`preset-${preset.id}`)}
            onMouseLeave={() => setHoveredCard(null)}
          />
        ))}
      </div>
    );
  };

  // Custom providers: configured rows not already shown under a preset card
  const customProviders = useMemo<ProviderRow[]>(() => {
    return providers
      .filter((p) => !isPresetProvider(p, presets))
      .sort((a, b) => {
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
        return a.id - b.id;
      });
  }, [providers, presets]);

  const hasContent = presets.length > 0 || providers.length > 0;

  return (
    <PageShell
      title={t("pageShell.models.title")}
      subtitle={t("pageShell.models.subtitle")}
      actions={
        modelCategory === "chat" ? (
          <Space>
            <Button
              icon={<RefreshCw size={14} />}
              onClick={() => void fetchAll()}
            >
              {t("common.refresh")}
            </Button>
          </Space>
        ) : null
      }
    >
      <Tabs
        activeKey={modelCategory}
        onChange={setModelCategory}
        items={[
          {
            key: "chat",
            label: (
              <Space size={6}>
                <MessageSquareText size={15} />
                {t("models.chatModelsTab")}
              </Space>
            ),
          },
          ...(canProviders
            ? [
                {
                  key: "generation",
                  label: (
                    <Space size={6}>
                      <Images size={15} />
                      {t("models.generationModelsTab")}
                    </Space>
                  ),
                },
              ]
            : []),
        ]}
      />
      {modelCategory === "generation" ? (
        <MediaGenerationSettingsPanel />
      ) : loading ? (
        <LoadingState message={t("models.loadingProviders")} />
      ) : error ? (
        <LoadingState message={error} error onRetry={() => void fetchAll()} />
      ) : !hasContent ? (
        <Empty description={t("models.noProvidersHint")} />
      ) : (
        <>
          <ActiveModelPool
            resolvedModels={resolvedModels}
            activeModel={activeModel}
            modelReasoning={modelReasoning}
            providers={providers}
            onSaved={fetchAll}
          />

          <Divider style={{ margin: "24px 0" }} />

          {showPresetSection && (
            <>
              <Title level={5} style={{ marginBottom: 12 }}>
                {t("models.presetProviders")}
              </Title>
              <Tabs
                items={[
                  showCloudTab
                    ? {
                        key: "cloud",
                        label: t("models.presetCloud"),
                        children: renderPresetGrid(
                          cloudPresets.grouped,
                          cloudPresets.ungrouped,
                        ),
                      }
                    : null,
                  showLocalTab
                    ? {
                        key: "local",
                        label: t("models.presetLocal"),
                        children: renderPresetGrid(
                          localPresets.grouped,
                          localPresets.ungrouped,
                        ),
                      }
                    : null,
                ].filter((item) => item !== null)}
              />
            </>
          )}

          {canProviders && (
            <>
              {(presets.length > 0 || customProviders.length > 0) && (
                <Divider style={{ margin: "20px 0" }} />
              )}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                }}
              >
                <Title level={5} style={{ margin: 0 }}>
                  {t("models.customProviders")}
                </Title>
                <Button
                  type="primary"
                  size="small"
                  icon={<Plus size={13} />}
                  onClick={() => setAddOpen(true)}
                >
                  {t("models.addCustomProvider")}
                </Button>
              </div>
              {customProviders.length > 0 ? (
                <div className={styles.providerCards}>
                  {customProviders.map((p) => (
                    <ProviderCard
                      key={p.id}
                      provider={p}
                      onSaved={fetchAll}
                      isHover={hoveredCard === String(p.id)}
                      onMouseEnter={() => setHoveredCard(String(p.id))}
                      onMouseLeave={() => setHoveredCard(null)}
                      apiPrefix="/admin/providers"
                    />
                  ))}
                </div>
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t("models.noCustomProvidersHint")}
                />
              )}
            </>
          )}
        </>
      )}

      {modelCategory === "chat" && (
        <CustomProviderModal
          open={addOpen && canProviders}
          onClose={() => setAddOpen(false)}
          onSaved={fetchAll}
          apiPrefix="/admin/providers"
        />
      )}
    </PageShell>
  );
}
