/**
 * EmbeddingSettingsPanel — manage embedding-only providers + ONNX.
 *
 * Logical split from the chat Models tab (scheme A): same providers table,
 * but ``purpose=embedding`` / ONNX rows are added and edited here.
 * Spacing / card grid mirror the chat Models tab.
 */
import { useCallback, useMemo, useRef, useState } from "react";
import { Divider, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type { ProviderPreset, ProviderRow } from "../useProviders";
import { isEmbeddingProvider } from "../useProviders";
import { findConfiguredProvider, isOnnxProviderRow } from "../presetUtils";
import { AddProviderCard } from "./cards/AddProviderCard";
import { LocalServiceCard } from "./cards/LocalServiceCard";
import { PresetProviderCard } from "./cards/PresetProviderCard";
import { ProviderCard } from "./cards/ProviderCard";
import { CustomProviderModal } from "./modals/CustomProviderModal";
import { EmbeddingModelPool } from "./EmbeddingModelPool";
import pageStyles from "../index.module.less";
import styles from "./EmbeddingSettingsPanel.module.less";

const { Paragraph, Title } = Typography;

interface EmbeddingSettingsPanelProps {
  providers: ProviderRow[];
  presets: ProviderPreset[];
  canProviders: boolean;
  canOnnx: boolean;
  onSaved: () => void | Promise<void>;
}

function isEmbeddingPreset(preset: ProviderPreset): boolean {
  return (
    preset.purpose === "embedding" || preset.provider_variant === "embedding"
  );
}

export function EmbeddingSettingsPanel({
  providers,
  presets,
  canProviders,
  canOnnx,
  onSaved,
}: EmbeddingSettingsPanelProps) {
  const { t } = useTranslation();
  const [addOpen, setAddOpen] = useState(false);
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);
  const [poolFlash, setPoolFlash] = useState(false);
  const servicesRef = useRef<HTMLDivElement>(null);
  const flashTimer = useRef<number | null>(null);

  const handleSaved = useCallback(async () => {
    await onSaved();
    setPoolFlash(true);
    if (flashTimer.current != null) window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => {
      setPoolFlash(false);
      flashTimer.current = null;
    }, 1600);
  }, [onSaved]);

  const scrollToServices = useCallback(() => {
    servicesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const onnxPreset = useMemo(
    () => presets.find((preset) => preset.id === "onnx") ?? null,
    [presets],
  );
  const onnxProvider = useMemo(() => {
    if (!onnxPreset) return null;
    return findConfiguredProvider(onnxPreset, providers) ?? null;
  }, [onnxPreset, providers]);

  const cloudEmbeddingPresets = useMemo(
    () =>
      presets.filter(
        (preset) => isEmbeddingPreset(preset) && preset.id !== "onnx",
      ),
    [presets],
  );

  /** Custom embedding providers not covered by a cloud preset card. */
  const customEmbeddingProviders = useMemo(() => {
    const presetKeys = new Set(
      cloudEmbeddingPresets.flatMap((preset) => [
        preset.id,
        preset.name,
        preset.name.toLowerCase(),
      ]),
    );
    return providers
      .filter(
        (provider) =>
          isEmbeddingProvider(provider) &&
          !isOnnxProviderRow(provider) &&
          !presetKeys.has(provider.name) &&
          !presetKeys.has(provider.name.toLowerCase()),
      )
      .sort((a, b) => {
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
        return a.id - b.id;
      });
  }, [providers, cloudEmbeddingPresets]);

  const showLocal = canOnnx && !!onnxPreset;
  const showCloud = canProviders;
  const showServices = showLocal || showCloud;

  return (
    <div className={styles.panel}>
      <Paragraph className={styles.intro}>
        {t("models.embeddingIntro")}
      </Paragraph>

      <EmbeddingModelPool
        providers={providers}
        flash={poolFlash}
        showServicesCta={showServices}
        onScrollToServices={scrollToServices}
      />

      {showServices ? (
        <>
          <Divider style={{ margin: "24px 0" }} />
          <div ref={servicesRef} className={styles.section}>
            <Title level={5} className={styles.sectionTitle}>
              {t("models.embeddingServicesSection")}
            </Title>
            <div
              className={`${pageStyles.providerCards} ${pageStyles.serviceCardsArea}`}
            >
              {showLocal && onnxPreset ? (
                <LocalServiceCard
                  preset={onnxPreset}
                  provider={onnxProvider}
                  onSaved={handleSaved}
                  isHover={hoveredCard === "onnx"}
                  onMouseEnter={() => setHoveredCard("onnx")}
                  onMouseLeave={() => setHoveredCard(null)}
                />
              ) : null}
              {showCloud
                ? cloudEmbeddingPresets.map((preset) => (
                    <PresetProviderCard
                      key={preset.id}
                      preset={preset}
                      providers={providers}
                      onSaved={handleSaved}
                      isHover={hoveredCard === `preset-${preset.id}`}
                      onMouseEnter={() => setHoveredCard(`preset-${preset.id}`)}
                      onMouseLeave={() => setHoveredCard(null)}
                    />
                  ))
                : null}
              {showCloud
                ? customEmbeddingProviders.map((provider) => (
                    <ProviderCard
                      key={provider.id}
                      provider={provider}
                      onSaved={handleSaved}
                      isHover={hoveredCard === `p-${provider.id}`}
                      onMouseEnter={() => setHoveredCard(`p-${provider.id}`)}
                      onMouseLeave={() => setHoveredCard(null)}
                      apiPrefix="/admin/providers"
                    />
                  ))
                : null}
              {showCloud ? (
                <AddProviderCard
                  onClick={() => setAddOpen(true)}
                  isHover={hoveredCard === "add"}
                  onMouseEnter={() => setHoveredCard("add")}
                  onMouseLeave={() => setHoveredCard(null)}
                />
              ) : null}
            </div>
          </div>
          {showCloud ? (
            <CustomProviderModal
              open={addOpen}
              onClose={() => setAddOpen(false)}
              onSaved={handleSaved}
              apiPrefix="/admin/providers"
              purpose="embedding"
            />
          ) : null}
        </>
      ) : null}
    </div>
  );
}
