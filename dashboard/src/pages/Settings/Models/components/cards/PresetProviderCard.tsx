/**
 * PresetProviderCard — card for a built-in preset provider.
 *
 * Local runtimes (Ollama / ONNX): always LocalServiceCard — service switch, no create CTA.
 * Cloud presets:
 *  - Not configured → gray card; click opens PresetProviderModal
 *  - Configured → ProviderCard
 */
import { useState } from "react";
import { Card, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { ProviderRow, ProviderPreset } from "../../useProviders";
import {
  findConfiguredProvider,
  isLocalPreset,
  presetLogoId,
} from "../../presetUtils";
import { ProviderCard } from "./ProviderCard";
import { LocalServiceCard } from "./LocalServiceCard";
import { PresetProviderModal } from "../modals/PresetProviderModal";
import {
  getProviderLogo,
  customProviderLogo,
} from "../../../../../assets/providers";
import styles from "../../index.module.less";

interface PresetProviderCardProps {
  preset: ProviderPreset;
  /** All configured providers so we can detect if this preset is already set up. */
  providers: ProviderRow[];
  onSaved: () => void | Promise<void>;
  isHover: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export function PresetProviderCard({
  preset,
  providers,
  onSaved,
  isHover,
  onMouseEnter,
  onMouseLeave,
}: PresetProviderCardProps) {
  const { t } = useTranslation();
  const [modalOpen, setModalOpen] = useState(false);

  const configured = findConfiguredProvider(preset, providers);
  const logo = getProviderLogo(presetLogoId(preset)) ?? customProviderLogo;

  if (isLocalPreset(preset)) {
    return (
      <LocalServiceCard
        preset={preset}
        provider={configured ?? null}
        onSaved={onSaved}
        isHover={isHover}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      />
    );
  }

  if (configured) {
    return (
      <ProviderCard
        provider={configured}
        onSaved={onSaved}
        isHover={isHover}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        apiPrefix="/admin/providers"
      />
    );
  }

  return (
    <>
      <Card
        hoverable
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        onClick={() => setModalOpen(true)}
        className={
          isHover
            ? `${styles.providerCard} ${styles.hover} ${styles.presetCard}`
            : `${styles.providerCard} ${styles.normal} ${styles.presetCard}`
        }
      >
        <div className={styles.cardContent}>
          <div className={styles.cardHeader}>
            <span className={styles.cardName}>
              {logo && (
                <img
                  src={logo}
                  alt={preset.name}
                  className={styles.providerLogo}
                />
              )}
              {preset.name}
            </span>
            <div className={styles.statusContainer}>
              <span className={`${styles.statusDot} ${styles.inactive}`} />
              <span className={`${styles.statusText} ${styles.disabled}`}>
                {t("models.presetNotConfigured")}
              </span>
            </div>
          </div>

          <div className={styles.cardInfo}>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>Base URL:</span>
              {preset.base_url ? (
                <span className={styles.infoValue} title={preset.base_url}>
                  {preset.base_url}
                </span>
              ) : (
                <span className={styles.infoEmpty}>{t("models.notSet")}</span>
              )}
            </div>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>{t("models.model")}:</span>
              <span className={styles.infoValue}>
                {preset.models.length > 0
                  ? t("models.modelsCount", { count: preset.models.length })
                  : t("models.noModels")}
              </span>
            </div>
          </div>
        </div>

        <div className={styles.cardActions}>
          <div className={styles.cardActionsLeft}>
            <Tag color="default" style={{ fontSize: 11 }}>
              {preset.protocol}
            </Tag>
          </div>
          <div className={styles.cardActionsRight}>
            <span style={{ fontSize: 12, color: "var(--fn-text-tertiary)" }}>
              {t("models.setupPreset", { name: preset.name })}
            </span>
          </div>
        </div>
      </Card>

      <PresetProviderModal
        preset={preset}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={onSaved}
      />
    </>
  );
}
