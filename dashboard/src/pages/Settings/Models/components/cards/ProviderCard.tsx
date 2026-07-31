/**
 * ProviderCard — admin card for one ProviderRow.
 *
 * All providers are admin-managed. Delete and edit are always available.
 */
import { useState } from "react";
import { Button, Card, Modal, Switch, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";

import { Pencil, Trash2, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../../../api/request";
import type { ProviderRow } from "../../useProviders";
import { ProviderConfigModal } from "../modals/ProviderConfigModal";
import {
  getProviderLogo,
  customProviderLogo,
} from "../../../../../assets/providers";
import styles from "../../index.module.less";

interface ProviderCardProps {
  provider: ProviderRow;
  onSaved: () => void | Promise<void>;
  isHover: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  /** API path prefix for PATCH/DELETE/test. Defaults to "/admin/providers". */
  apiPrefix?: string;
}

export function ProviderCard({
  provider,
  onSaved,
  isHover,
  onMouseEnter,
  onMouseLeave,
  apiPrefix = "/admin/providers",
}: ProviderCardProps) {
  const { t } = useTranslation();
  const [modalOpen, setModalOpen] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toggling, setToggling] = useState(false);

  const hasApiKey = !!provider.api_key && provider.api_key.length > 0;
  const statusReady = hasApiKey;
  const statusLabel = hasApiKey
    ? t("models.authorized")
    : t("models.unauthorized");

  const handleTestConnection = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setTesting(true);
    try {
      // NOTE: request() auto-prefixes /api. Pass the bare path —
      // a previous bug at this call site double-prefixed.
      const result = await request<{
        ok: boolean;
        latency_ms?: number;
        error?: string;
      }>(`${apiPrefix}/${provider.id}/test`, { method: "POST" });
      if (result.ok) {
        const latency =
          result.latency_ms != null
            ? t("models.testConnectionLatency", { time: result.latency_ms })
            : "";
        message.success(
          t("models.testConnectionSuccess", {
            name: provider.name,
            latency,
          }),
        );
      } else {
        message.error(
          t("models.testConnectionFailed", {
            error: result.error ?? "unknown",
          }),
        );
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(t("models.testConnectionFailed", { error: msg }));
    } finally {
      setTesting(false);
    }
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    Modal.confirm({
      title: t("models.deleteProviderTitle"),
      content: t("models.deleteProviderConfirmSimple", { name: provider.name }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await request(`${apiPrefix}/${provider.id}`, { method: "DELETE" });
          message.success(
            t("models.providerDeletedSimple", { name: provider.name }),
          );
          await onSaved();
        } catch (err) {
          message.error(
            err instanceof Error
              ? err.message
              : t("models.deleteProviderFailedSimple"),
          );
        }
      },
    });
  };

  const handleToggle = async (next: boolean) => {
    setToggling(true);
    try {
      await request(`${apiPrefix}/${provider.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: next }),
      });
      await onSaved();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("models.toggleStateFailed"),
      );
    } finally {
      setToggling(false);
    }
  };

  // Mask api_key for display: show first 4 + last 4, mask middle.
  const maskedKey = (() => {
    if (!provider.api_key) return null;
    const k = provider.api_key;
    if (k.length <= 10) return "•".repeat(k.length);
    return `${k.slice(0, 4)}${"•".repeat(6)}${k.slice(-4)}`;
  })();

  // Try lookup by name, lowercase name, then fall back to custom logo.
  // Provider names like "DeepSeek" → "deepseek", "Tencent Cloud Coding Plan" → try both.
  const nameSlug = provider.name.toLowerCase().replace(/\s+/g, "-");
  const logo =
    getProviderLogo(provider.name) ??
    getProviderLogo(provider.name.toLowerCase()) ??
    getProviderLogo(nameSlug) ??
    customProviderLogo;
  const models = provider.models ?? [];

  return (
    <>
      <Card
        hoverable
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        className={
          isHover
            ? `${styles.providerCard} ${styles.hover}`
            : statusReady
            ? `${styles.providerCard} ${styles.enabled}`
            : `${styles.providerCard} ${styles.normal}`
        }
        style={{ opacity: provider.enabled ? 1 : 0.7 }}
      >
        <div className={styles.cardContent}>
          <div className={styles.cardHeader}>
            <span className={styles.cardName}>
              {logo && (
                <img
                  src={logo}
                  alt={provider.name}
                  className={styles.providerLogo}
                />
              )}
              <span title={provider.name}>{provider.name}</span>
            </span>
            <div className={styles.statusContainer}>
              <span
                className={`${styles.statusDot} ${
                  statusReady ? styles.active : styles.inactive
                }`}
              />
              <span
                className={`${styles.statusText} ${
                  statusReady ? styles.enabled : styles.disabled
                }`}
              >
                {statusLabel}
              </span>
            </div>
          </div>

          <div className={styles.cardInfo}>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>Base URL:</span>
              {provider.base_url ? (
                <span className={styles.infoValue} title={provider.base_url}>
                  {provider.base_url}
                </span>
              ) : (
                <span className={styles.infoEmpty}>{t("models.notSet")}</span>
              )}
            </div>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>API Key:</span>
              {maskedKey ? (
                <span className={styles.infoValue}>{maskedKey}</span>
              ) : (
                <span className={styles.infoEmpty}>{t("models.notSet")}</span>
              )}
            </div>
            <div className={styles.infoRowModels}>
              <span className={styles.infoLabel}>{t("models.model")}:</span>
              {models.length > 0 ? (
                <span className={styles.infoValue}>
                  {t("models.modelsCount", { count: models.length })}
                </span>
              ) : (
                <span className={styles.infoEmpty}>{t("models.noModels")}</span>
              )}
            </div>
            {provider.note && (
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>
                  {t("models.noteLabelShort")}:
                </span>
                <span className={styles.infoValue} title={provider.note}>
                  {provider.note}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className={styles.cardActions}>
          <div className={styles.cardActionsLeft}>
            <Switch
              size="small"
              checked={provider.enabled}
              loading={toggling}
              onChange={(c) => void handleToggle(c)}
              onClick={(_, e) => e.stopPropagation()}
            />
            <span className={styles.cardActionsStatus}>
              {provider.enabled ? t("common.enabled") : t("common.disabled")}
            </span>
          </div>
          <div className={styles.cardActionsRight}>
            {hasApiKey && (
              <Tooltip title={t("models.test")}>
                <Button
                  type="text"
                  size="small"
                  loading={testing}
                  onClick={handleTestConnection}
                  className={styles.cardActionBtn}
                  icon={<Zap size={14} />}
                />
              </Tooltip>
            )}
            <Tooltip title={t("models.settings")}>
              <Button
                type="text"
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  setModalOpen(true);
                }}
                className={styles.cardActionBtn}
                icon={<Pencil size={14} />}
              />
            </Tooltip>
            <Tooltip title={t("common.delete")}>
              <Button
                type="text"
                size="small"
                danger
                onClick={handleDelete}
                className={styles.cardActionBtn}
                icon={<Trash2 size={14} />}
              />
            </Tooltip>
          </div>
        </div>
      </Card>

      <ProviderConfigModal
        provider={provider}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={onSaved}
        apiPrefix={apiPrefix}
      />
    </>
  );
}
