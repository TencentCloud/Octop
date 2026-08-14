/**
 * LocalServiceCard — always-on card for Ollama / ONNX local runtimes.
 *
 * No "create/setup" CTA. One service switch controls whether the runtime is on.
 * Opening settings auto-provisions the provider row when missing, then opens config.
 */
import { useEffect, useState } from "react";
import { Button, Card, Modal, Switch, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";
import { Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../../../api/request";
import { ollamaModelApi } from "../../../../../api/modules/ollamaModel";
import { onnxModelApi } from "../../../../../api/modules/onnxModel";
import {
  getProviderLogo,
  customProviderLogo,
} from "../../../../../assets/providers";
import type {
  ProviderModel,
  ProviderPreset,
  ProviderRow,
} from "../../useProviders";
import { presetLogoId } from "../../presetUtils";
import { ProviderConfigModal } from "../modals/ProviderConfigModal";
import styles from "../../index.module.less";

interface LocalServiceCardProps {
  preset: ProviderPreset;
  provider: ProviderRow | null;
  onSaved: () => void | Promise<void>;
  isHover: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

function presetModelsToRows(preset: ProviderPreset): ProviderModel[] {
  return preset.models.map((m) => ({
    id: m.id,
    name: m.name,
    enabled: false,
    embedding: preset.id === "onnx" ? true : undefined,
    task: preset.id === "onnx" ? "embedding" : undefined,
    input: m.input?.length ? m.input : ["text"],
    thinking: null,
  }));
}

export function LocalServiceCard({
  preset,
  provider,
  onSaved,
  isHover,
  onMouseEnter,
  onMouseLeave,
}: LocalServiceCardProps) {
  const { t } = useTranslation();
  const isOnnx = preset.id === "onnx";
  const [serviceEnabled, setServiceEnabled] = useState(false);
  const [serviceRunning, setServiceRunning] = useState(false);
  const [serviceBusy, setServiceBusy] = useState(false);
  const [depsAvailable, setDepsAvailable] = useState(true);
  const [depsInstallFailed, setDepsInstallFailed] = useState(false);
  const [ensuring, setEnsuring] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [row, setRow] = useState<ProviderRow | null>(provider);

  useEffect(() => {
    setRow(provider);
  }, [provider]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        if (isOnnx) {
          const st = await onnxModelApi.getStatus();
          if (!cancelled) {
            setServiceEnabled(st.enabled);
            setServiceRunning(st.ready || st.enabled);
            setDepsAvailable(st.deps_available !== false);
            setDepsInstallFailed(false);
          }
        } else {
          const st = await ollamaModelApi.getService();
          if (!cancelled) {
            setServiceEnabled(st.enabled);
            setServiceRunning(st.running);
            setDepsAvailable(true);
            setDepsInstallFailed(false);
          }
        }
      } catch {
        if (!cancelled) {
          setServiceEnabled(false);
          setServiceRunning(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOnnx, provider?.id]);

  const ensureProvider = async (): Promise<ProviderRow> => {
    if (row) return row;
    setEnsuring(true);
    try {
      const created = await request<ProviderRow>("/admin/providers", {
        method: "POST",
        body: JSON.stringify({
          name: preset.name,
          kind: preset.protocol,
          base_url: preset.base_url || null,
          api_key: preset.id,
          models: presetModelsToRows(preset),
          enabled: false,
        }),
      });
      setRow(created);
      await onSaved();
      return created;
    } finally {
      setEnsuring(false);
    }
  };

  const handleServiceToggle = async (next: boolean) => {
    setServiceBusy(true);
    try {
      const ensured = await ensureProvider();
      if (isOnnx) {
        const st = await onnxModelApi.setService(next);
        setServiceEnabled(st.enabled);
        setServiceRunning(st.ready || st.enabled);
        setDepsAvailable(st.deps_available !== false);
        setDepsInstallFailed(false);
      } else {
        const st = await ollamaModelApi.setService(next);
        setServiceEnabled(st.enabled);
        setServiceRunning(st.running);
      }
      await request(`/admin/providers/${ensured.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: next }),
      });
      await onSaved();
      message.success(
        next
          ? t("models.localServiceStarted")
          : t("models.localServiceStopped"),
      );
    } catch (err) {
      if (isOnnx && next) {
        setDepsInstallFailed(true);
        setDepsAvailable(false);
      }
      message.error(
        err instanceof Error
          ? err.message
          : t("models.localServiceToggleFailed"),
      );
    } finally {
      setServiceBusy(false);
    }
  };

  const handleOpenSettings = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await ensureProvider();
      setModalOpen(true);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("models.createFailedSimple"),
      );
    }
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!row) return;
    Modal.confirm({
      title: t("models.deleteProviderTitle"),
      content: t("models.deleteProviderConfirmSimple", { name: row.name }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await request(`/admin/providers/${row.id}`, { method: "DELETE" });
          setRow(null);
          setModalOpen(false);
          message.success(
            t("models.providerDeletedSimple", { name: row.name }),
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

  const logo = getProviderLogo(presetLogoId(preset)) ?? customProviderLogo;
  const models = row?.models ?? preset.models;
  const baseUrl = row?.base_url ?? preset.base_url;

  return (
    <>
      <Card
        hoverable
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        className={
          isHover
            ? `${styles.providerCard} ${styles.hover}`
            : serviceEnabled
            ? `${styles.providerCard} ${styles.enabled}`
            : `${styles.providerCard} ${styles.normal}`
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
              <span title={preset.name}>{preset.name}</span>
            </span>
            <div className={styles.statusContainer}>
              <span
                className={`${styles.statusDot} ${
                  serviceRunning ? styles.active : styles.inactive
                }`}
              />
              <span
                className={`${styles.statusText} ${
                  serviceEnabled ? styles.enabled : styles.disabled
                }`}
              >
                {serviceEnabled
                  ? serviceRunning
                    ? t("models.localServiceRunning")
                    : t("models.localServiceOn")
                  : t("models.localServiceOff")}
              </span>
            </div>
          </div>

          <div className={styles.cardInfo}>
            {!isOnnx && (
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Base URL:</span>
                {baseUrl ? (
                  <span className={styles.infoValue} title={baseUrl}>
                    {baseUrl}
                  </span>
                ) : (
                  <span className={styles.infoEmpty}>
                    {t("models.localRuntime")}
                  </span>
                )}
              </div>
            )}
            <div className={styles.infoRowModels}>
              <span className={styles.infoLabel}>{t("models.model")}:</span>
              <span className={styles.infoValue}>
                {models.length > 0
                  ? t("models.modelsCount", { count: models.length })
                  : t("models.noModels")}
              </span>
            </div>
            {isOnnx && !depsAvailable && (
              <div className={styles.infoRow}>
                <span
                  className={styles.infoEmpty}
                  style={{ whiteSpace: "normal", lineHeight: 1.4 }}
                >
                  {depsInstallFailed
                    ? t("models.onnxDepsInstallFailed")
                    : t("models.onnxDepsPending")}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className={styles.cardActions}>
          <div className={styles.cardActionsLeft}>
            <Tooltip title={t("models.localServiceHint")}>
              <Switch
                size="small"
                checked={serviceEnabled}
                loading={serviceBusy || ensuring}
                onChange={(c) => void handleServiceToggle(c)}
                onClick={(_, e) => e.stopPropagation()}
              />
            </Tooltip>
            <span className={styles.cardActionsStatus}>
              {t("models.localServiceLabel")}
            </span>
          </div>
          <div className={styles.cardActionsRight}>
            <Tooltip title={t("models.settings")}>
              <Button
                type="text"
                size="small"
                loading={ensuring}
                onClick={(e) => void handleOpenSettings(e)}
                className={styles.cardActionBtn}
                icon={<Pencil size={14} />}
              />
            </Tooltip>
            {row && (
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
            )}
          </div>
        </div>
      </Card>

      {row && (
        <ProviderConfigModal
          provider={row}
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          onSaved={async () => {
            await onSaved();
          }}
          apiPrefix="/admin/providers"
        />
      )}
    </>
  );
}
