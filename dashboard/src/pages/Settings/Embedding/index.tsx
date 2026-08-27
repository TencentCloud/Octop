import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { App, Select, Input, Button, Spin, Progress, Alert } from "antd";

import { Download, CheckCircle, AlertCircle } from "lucide-react";
import api from "../../../api";
import type { EmbeddingConfig } from "../../../api/types/embedding";
import { useEmbeddingDownloadWS } from "../../../hooks/useEmbeddingDownloadWS";
import {
  formatDuration,
  getDownloadSpeed,
  getDownloadTransferred,
} from "../../../utils/embeddingDownload";
import styles from "./index.module.less";

export default function EmbeddingPage() {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();

  // State management.
  const [config, setConfig] = useState<EmbeddingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [presetModels, setPresetModels] = useState<string[]>([]);

  const { downloadState, refreshDownloadStatus } = useEmbeddingDownloadWS();
  const prevStatusRef = useRef<string | null>(null);

  // Load config and preset model list.
  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const [cfg, models] = await Promise.all([
          api.getConfig(),
          api.getPresetModels(),
        ]);
        setConfig(cfg);
        setPresetModels(models);
      } catch (err) {
        message.error(t("embedding.loadError"));
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [t]);

  // Handle download completion/failure notifications from status polling.
  useEffect(() => {
    if (!downloadState) return;

    const prev = prevStatusRef.current;
    const curr = downloadState.status;
    prevStatusRef.current = curr;

    if (prev === curr) return;

    if (curr === "done") {
      if (prev === "loading") {
        message.success(t("embedding.loadComplete"));
      } else if (prev === "downloading") {
        message.success(t("embedding.downloadComplete"));
      }
      api
        .getConfig()
        .then((cfg) => setConfig(cfg))
        .catch(console.error);
    } else if (curr === "failed") {
      const fallbackMessage =
        prev === "loading"
          ? t("embedding.loadFailed")
          : t("embedding.downloadFailed");
      message.error(downloadState.error || fallbackMessage);
    }
  }, [downloadState, t]);

  // Save config.
  const handleSaveConfig = useCallback(async () => {
    if (!config) return;
    try {
      setSaving(true);
      const updated = await api.updateConfig(config);
      setConfig(updated);
      message.success(t("common.saveSuccess"));
    } catch (err) {
      message.error(t("common.saveFailed"));
      console.error(err);
    } finally {
      setSaving(false);
    }
  }, [config, t]);

  const handleApplyConfig = useCallback(async () => {
    if (!config) return;
    try {
      setApplying(true);
      const updated = await api.applyConfig(config);
      setConfig(updated);
      const state = await refreshDownloadStatus();

      if (updated.provider === "local") {
        if (state?.status === "loading") {
          message.info(t("embedding.loadStarted"));
        } else if (state?.status === "downloading") {
          message.info(t("embedding.downloadStarted"));
        }
      } else {
        message.success(t("embedding.applySuccess"));
      }
    } catch (err) {
      message.error(t("common.saveFailed"));
      console.error(err);
    } finally {
      setApplying(false);
    }
  }, [config, refreshDownloadStatus, t]);

  const handleDisableVectorSearch = useCallback(() => {
    if (!config || config.provider === "none") return;
    modal.confirm({
      title: t("embedding.disableVectorConfirmTitle"),
      content: t("embedding.disableVectorConfirmDesc"),
      okText: t("common.disable"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      async onOk() {
        try {
          setApplying(true);
          const next = { ...config, provider: "none" as const };
          const updated = await api.applyConfig(next);
          setConfig(updated);
          message.success(t("embedding.disableVectorSuccess"));
          await refreshDownloadStatus();
        } catch (err) {
          message.error(t("common.saveFailed"));
          console.error(err);
        } finally {
          setApplying(false);
        }
      },
    });
  }, [config, refreshDownloadStatus, t]);

  // Trigger local model download; polling picks up backend status changes.
  const handleDownloadLocalModel = useCallback(async () => {
    try {
      await api.downloadLocalModel(config?.localModel || "");
      const state = await refreshDownloadStatus();
      if (state?.status === "loading") {
        message.info(t("embedding.loadStarted"));
      } else if (state?.status === "downloading") {
        message.info(t("embedding.downloadStarted"));
      }
    } catch (err) {
      message.error(t("embedding.downloadError"));
      console.error(err);
    }
  }, [config?.localModel, t, refreshDownloadStatus]);

  // Update a config field.
  const updateConfig = (field: keyof EmbeddingConfig, value: unknown) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  if (loading || !config) {
    return (
      <div className={styles.page}>
        <Spin size="large" />
      </div>
    );
  }

  const isStatusBusy =
    downloadState?.status === "loading" ||
    downloadState?.status === "downloading";
  const appliedProvider = downloadState?.applied_provider ?? "none";
  const appliedModelName = downloadState?.applied_model_name || "-";
  const appliedStatus = (() => {
    if (!downloadState) return "idle";
    if (downloadState.applied_provider === "custom") {
      return downloadState.ready ? "done" : "failed";
    }
    if (downloadState.applied_provider === "none") {
      return "idle";
    }
    return downloadState.status;
  })();
  const appliedProviderLabel =
    appliedProvider === "local"
      ? t("embedding.modeLocal")
      : appliedProvider === "custom"
      ? t("embedding.modeCustom")
      : t("common.disabled");

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t("embedding.title")}</h2>
        <p className={styles.description}>{t("embedding.description")}</p>
      </div>

      <Alert
        type="warning"
        showIcon
        message={t("embedding.vectorIndexWarning")}
        className={styles.vectorIndexAlert}
      />

      <div className={styles.appliedCard}>
        <div className={styles.appliedHeader}>
          <h3 className={styles.sectionTitle}>
            {t("embedding.currentApplied")}
          </h3>
          <span className={`${styles.statusBadge} ${styles[appliedStatus]}`}>
            {appliedStatus === "loading"
              ? t("embedding.loading")
              : appliedStatus === "downloading"
              ? t("embedding.downloading")
              : appliedStatus === "done"
              ? t("embedding.done")
              : appliedStatus === "failed"
              ? t("embedding.failed")
              : t("embedding.idle")}
          </span>
        </div>
        <div className={styles.appliedGrid}>
          <div className={styles.appliedItem}>
            <span className={styles.appliedLabel}>
              {t("embedding.provider")}
            </span>
            <span className={styles.appliedValue}>{appliedProviderLabel}</span>
          </div>
          <div className={styles.appliedItem}>
            <span className={styles.appliedLabel}>
              {t("embedding.modelName")}
            </span>
            <span className={styles.appliedValue}>{appliedModelName}</span>
          </div>
        </div>
      </div>

      {/* Provider Radio Buttons */}
      <div className={styles.card}>
        <div className={styles.providerHeader}>
          <h3 className={styles.sectionTitle}>{t("embedding.provider")}</h3>
          {config.provider !== "none" && (
            <Button
              danger
              type="default"
              onClick={handleDisableVectorSearch}
              disabled={saving || applying}
            >
              {t("embedding.disableVectorSearch")}
            </Button>
          )}
        </div>

        <div className={styles.radioGroup}>
          {/* Option 1: None */}
          <label className={styles.radioOption}>
            <input
              type="radio"
              name="provider"
              value="none"
              checked={config.provider === "none"}
              onChange={() => updateConfig("provider", "none")}
            />
            <div className={styles.radioContent}>
              <span className={styles.radioLabel}>{t("common.disabled")}</span>
              <span className={styles.radioDesc}>
                {t("embedding.modeNoneDesc")}
              </span>
            </div>
          </label>

          {/* Option 2: Local */}
          <label className={styles.radioOption}>
            <input
              type="radio"
              name="provider"
              value="local"
              checked={config.provider === "local"}
              onChange={() => updateConfig("provider", "local")}
            />
            <div className={styles.radioContent}>
              <span className={styles.radioLabel}>
                {t("embedding.modeLocal")}
              </span>
              <span className={styles.radioDesc}>
                {t("embedding.modeLocalDesc")}
              </span>
            </div>
          </label>

          {/* Option 3: Custom */}
          <label className={styles.radioOption}>
            <input
              type="radio"
              name="provider"
              value="custom"
              checked={config.provider === "custom"}
              onChange={() => updateConfig("provider", "custom")}
            />
            <div className={styles.radioContent}>
              <span className={styles.radioLabel}>
                {t("embedding.modeCustom")}
              </span>
              <span className={styles.radioDesc}>
                {t("embedding.modeCustomDesc")}
              </span>
            </div>
          </label>
        </div>
      </div>

      {/* Local Mode Section */}
      {config.provider === "local" && (
        <div className={styles.card}>
          <h3 className={styles.sectionTitle}>{t("embedding.localConfig")}</h3>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("embedding.modelName")}</label>
            <Select
              value={config.localModel}
              onChange={(value) => updateConfig("localModel", value)}
              options={presetModels.map((model) => ({
                label: model,
                value: model,
              }))}
              placeholder={t("embedding.selectModel") || "Select a model"}
              className={styles.select}
            />
            <span className={styles.hint}>{t("embedding.modelNameHint")}</span>
          </div>

          {/* Download status, shown only when polling state matches the selected localModel */}
          {downloadState &&
            (() => {
              const currentModel = config.localModel || "";
              const isActiveDownload =
                !!downloadState.model_name &&
                downloadState.model_name === currentModel;
              const displayStatus = isActiveDownload
                ? downloadState.status
                : "idle";
              return (
                <div className={styles.downloadStatus}>
                  <div className={styles.statusHeader}>
                    <span className={styles.statusLabel}>
                      {t("embedding.downloadStatus")}
                    </span>
                    <span
                      className={`${styles.statusBadge} ${styles[displayStatus]}`}
                    >
                      {displayStatus === "loading"
                        ? t("embedding.loading")
                        : displayStatus === "downloading"
                        ? t("embedding.downloading")
                        : displayStatus === "done"
                        ? t("embedding.done")
                        : displayStatus === "failed"
                        ? t("embedding.failed")
                        : t("embedding.idle")}
                    </span>
                  </div>

                  {displayStatus === "loading" && (
                    <div className={styles.statusSuccess}>
                      <Spin size="small" />
                      <span>{t("embedding.loadStarted")}</span>
                    </div>
                  )}

                  {displayStatus === "downloading" && (
                    <>
                      <div className={styles.progressBar}>
                        <Progress
                          percent={Math.round(downloadState.progress * 100)}
                          status="active"
                        />
                      </div>
                      <div className={styles.downloadMeta}>
                        <span>
                          {t("embedding.downloaded")}:{" "}
                          {getDownloadTransferred(downloadState)}
                        </span>
                        <span>
                          {t("embedding.speed")}:{" "}
                          {getDownloadSpeed(downloadState)}
                        </span>
                        <span>
                          {t("embedding.elapsed")}:{" "}
                          {formatDuration(downloadState.elapsed_seconds)}
                        </span>
                        <span>
                          {t("embedding.remaining")}:{" "}
                          {formatDuration(downloadState.eta_seconds)}
                        </span>
                      </div>
                    </>
                  )}

                  {displayStatus === "done" && (
                    <div className={styles.statusSuccess}>
                      <CheckCircle size={16} />
                      <span>{t("embedding.ready")}</span>
                    </div>
                  )}

                  {displayStatus === "failed" && (
                    <div className={styles.statusError}>
                      <AlertCircle size={16} />
                      <span>
                        {downloadState.error || t("embedding.downloadFailed")}
                      </span>
                    </div>
                  )}
                </div>
              );
            })()}

          <Button
            type="primary"
            icon={<Download size={16} />}
            onClick={handleDownloadLocalModel}
            loading={isStatusBusy}
            disabled={isStatusBusy}
            className={styles.downloadBtn}
          >
            {t("embedding.downloadModel")}
          </Button>
        </div>
      )}

      {/* Custom Mode Section */}
      {config.provider === "custom" && (
        <div className={styles.card}>
          <h3 className={styles.sectionTitle}>{t("embedding.customConfig")}</h3>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("embedding.apiKey")}</label>
            <Input.Password
              value={config.apiKey}
              onChange={(e) => updateConfig("apiKey", e.target.value)}
              placeholder="sk-xxx..."
              className={styles.input}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("embedding.baseUrl")}</label>
            <Input
              value={config.baseUrl}
              onChange={(e) => updateConfig("baseUrl", e.target.value)}
              placeholder="https://api.example.com/v1"
              className={styles.input}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("embedding.modelName")}</label>
            <Input
              value={config.modelName}
              onChange={(e) => updateConfig("modelName", e.target.value)}
              placeholder="text-embedding-3-small"
              className={styles.input}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("embedding.dimensions")}</label>
            <Input
              type="number"
              value={config.dimensions}
              onChange={(e) =>
                updateConfig("dimensions", parseInt(e.target.value) || 512)
              }
              min={1}
              className={styles.input}
            />
          </div>
        </div>
      )}

      {/* Save Button */}
      <div className={styles.actions}>
        <Button
          onClick={handleSaveConfig}
          loading={saving}
          size="large"
          disabled={applying}
        >
          {t("common.save")}
        </Button>
        <Button
          type="primary"
          onClick={handleApplyConfig}
          loading={applying}
          size="large"
          disabled={saving}
        >
          {t("embedding.saveAndApply")}
        </Button>
      </div>
    </div>
  );
}
