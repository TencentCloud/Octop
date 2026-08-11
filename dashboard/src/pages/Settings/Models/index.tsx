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
import { Plus, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
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

const { Title } = Typography;

export default function ModelsPage() {
  const { t } = useTranslation();
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

  const cloudPresets = useMemo(
    () => groupPresets(presets.filter((p) => !isLocalPreset(p))),
    [presets],
  );
  const localPresets = useMemo(
    () => groupPresets(presets.filter((p) => isLocalPreset(p))),
    [presets],
  );

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
        <Space>
          <Button
            icon={<RefreshCw size={14} />}
            onClick={() => void fetchAll()}
          >
            {t("common.refresh")}
          </Button>
        </Space>
      }
    >
      {loading ? (
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

          {/* Preset providers section */}
          {presets.length > 0 && (
            <>
              <Title level={5} style={{ marginBottom: 12 }}>
                {t("models.presetProviders")}
              </Title>
              <Tabs
                items={[
                  {
                    key: "cloud",
                    label: t("models.presetCloud"),
                    children: renderPresetGrid(
                      cloudPresets.grouped,
                      cloudPresets.ungrouped,
                    ),
                  },
                  {
                    key: "local",
                    label: t("models.presetLocal"),
                    children: renderPresetGrid(
                      localPresets.grouped,
                      localPresets.ungrouped,
                    ),
                  },
                ]}
              />
            </>
          )}

          {/* Custom providers section — title row with inline "+ add" button */}
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
        </>
      )}

      <CustomProviderModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSaved={fetchAll}
        apiPrefix="/admin/providers"
      />
    </PageShell>
  );
}
