/**
 * PresetGroupCard — card for a multi-site brand (Kimi, MiniMax, Aliyun, …).
 *
 * Unconfigured: click opens site/variant picker, then PresetProviderModal.
 * Configured: segmented tabs switch between site-specific ProviderCards.
 */
import { useMemo, useState } from "react";
import { Card, Drawer, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { ProviderPreset, ProviderRow } from "../../useProviders";
import {
  findConfiguredProvider,
  presetLogoId,
  presetVariantLabel,
  type PresetGroup,
} from "../../presetUtils";
import { ProviderCard } from "./ProviderCard";
import { PresetProviderModal } from "../modals/PresetProviderModal";
import {
  getProviderLogo,
  customProviderLogo,
} from "../../../../../assets/providers";
import styles from "../../index.module.less";

interface PresetGroupCardProps {
  group: PresetGroup;
  providers: ProviderRow[];
  onSaved: () => void | Promise<void>;
  isHover: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

function VariantPickerDrawer({
  group,
  providers,
  open,
  onClose,
  onSelect,
}: {
  group: PresetGroup;
  providers: ProviderRow[];
  open: boolean;
  onClose: () => void;
  onSelect: (preset: ProviderPreset) => void;
}) {
  const { t } = useTranslation();

  return (
    <Drawer
      title={t("models.selectVariant", { name: group.groupName })}
      open={open}
      footer={null}
      onClose={onClose}
      destroyOnHidden
      width={480}
      placement="right"
    >
      <div className={styles.variantList}>
        {group.presets.map((preset) => {
          const configured = findConfiguredProvider(preset, providers);
          return (
            <div
              key={preset.id}
              className={
                configured
                  ? `${styles.variantItem} ${styles.variantItemDisabled}`
                  : styles.variantItem
              }
              onClick={() => {
                if (configured) return;
                onClose();
                onSelect(preset);
              }}
            >
              <span className={styles.variantItemName}>
                {presetVariantLabel(preset)}
              </span>
              <span className={styles.variantItemMeta}>{preset.base_url}</span>
              {configured && (
                <Tag color="success" style={{ marginLeft: 8 }}>
                  {t("models.configured")}
                </Tag>
              )}
            </div>
          );
        })}
      </div>
    </Drawer>
  );
}

export function PresetGroupCard({
  group,
  providers,
  onSaved,
  isHover,
  onMouseEnter,
  onMouseLeave,
}: PresetGroupCardProps) {
  const { t } = useTranslation();
  const [variantPickerOpen, setVariantPickerOpen] = useState(false);
  const [setupPreset, setSetupPreset] = useState<ProviderPreset | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);

  const configuredEntries = useMemo(
    () =>
      group.presets
        .map((preset) => ({
          preset,
          provider: findConfiguredProvider(preset, providers),
        }))
        .filter(
          (entry): entry is { preset: ProviderPreset; provider: ProviderRow } =>
            !!entry.provider,
        ),
    [group.presets, providers],
  );

  const logo =
    getProviderLogo(presetLogoId(group.presets[0])) ?? customProviderLogo;

  const variantDrawer = (
    <>
      <VariantPickerDrawer
        group={group}
        providers={providers}
        open={variantPickerOpen}
        onClose={() => setVariantPickerOpen(false)}
        onSelect={setSetupPreset}
      />
      {setupPreset && (
        <PresetProviderModal
          preset={setupPreset}
          open={!!setupPreset}
          onClose={() => setSetupPreset(null)}
          onSaved={onSaved}
        />
      )}
    </>
  );

  if (configuredEntries.length > 0) {
    const activeEntry = configuredEntries[activeIdx] ?? configuredEntries[0];
    return (
      <div className={styles.presetGroupWrap}>
        <div className={styles.presetGroupHeader}>
          {logo && (
            <img
              src={logo}
              alt={group.groupName}
              className={styles.providerLogo}
            />
          )}
          <span className={styles.presetGroupTitle}>{group.groupName}</span>
          <Tag color="default" style={{ fontSize: 11, marginLeft: "auto" }}>
            {configuredEntries.length}/{group.presets.length}
          </Tag>
        </div>
        {configuredEntries.length > 1 && (
          <div className={styles.presetGroupSegmented}>
            {configuredEntries.map((entry, idx) => (
              <button
                key={entry.preset.id}
                type="button"
                className={
                  idx === activeIdx
                    ? `${styles.presetGroupSegBtn} ${styles.presetGroupSegBtnActive}`
                    : styles.presetGroupSegBtn
                }
                onClick={() => setActiveIdx(idx)}
              >
                {presetVariantLabel(entry.preset)}
              </button>
            ))}
          </div>
        )}
        <ProviderCard
          provider={activeEntry.provider}
          onSaved={onSaved}
          isHover={isHover}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
          apiPrefix="/admin/providers"
        />
        <div className={styles.presetGroupFooter}>
          <button
            type="button"
            className={styles.presetGroupAddSite}
            onClick={() => setVariantPickerOpen(true)}
          >
            {t("models.addSiteVariant")}
          </button>
        </div>
        {variantDrawer}
      </div>
    );
  }

  return (
    <>
      <Card
        hoverable
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        onClick={() => setVariantPickerOpen(true)}
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
                  alt={group.groupName}
                  className={styles.providerLogo}
                />
              )}
              {group.groupName}
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
              <span className={styles.infoLabel}>{t("models.sites")}:</span>
              <span className={styles.infoValue}>
                {t("models.sitesCount", { count: group.presets.length })}
              </span>
            </div>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>{t("models.model")}:</span>
              <span className={styles.infoValue}>
                {t("models.chooseSiteFirst")}
              </span>
            </div>
          </div>
        </div>

        <div className={styles.cardActions}>
          <div className={styles.cardActionsLeft}>
            <Tag color="default" style={{ fontSize: 11 }}>
              {group.presets[0]?.protocol}
            </Tag>
          </div>
          <div className={styles.cardActionsRight}>
            <span style={{ fontSize: 12, color: "var(--fn-text-tertiary)" }}>
              {t("models.setupPreset", { name: group.groupName })}
            </span>
          </div>
        </div>
      </Card>
      {variantDrawer}
    </>
  );
}
