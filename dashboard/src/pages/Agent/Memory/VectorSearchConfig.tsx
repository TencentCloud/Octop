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
import styles from "./VectorSearchConfig.module.less";

export default function VectorSearchConfig() {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();

  const [config, setConfig] = useState<EmbeddingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [presetModels, setPresetModels] = useState<string[]>([]);
  // Downloaded model list, persisted to localStorage so service restarts do not lose state.
  const [downloadedModels, setDownloadedModels] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("lc_downloaded_models") || "[]");
    } catch {
      return [];
    }
  });

  // Download status via polling/WebSocket hook; keep refreshing after completion for later downloads.
  const { downloadState, refreshDownloadStatus } = useEmbeddingDownloadWS();
  // Track previous status to avoid duplicate notifications after remounts.
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
        // Preserve provider as returned by the backend; defaults are handled server-side.
        setConfig(cfg);
        setPresetModels(models);
      } catch (err) {
        message.error(t("memory.vs.loadError"));
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [t]);

  // Save config.
  const handleSaveConfig = useCallback(async () => {
    if (!config) return;
    try {
      setSaving(true);
      const updated = await api.updateConfig(config);
      setConfig(updated);
      message.success(t("memory.vs.saveSuccess"));
    } catch (err) {
      message.error(t("common.saveFailed") || "Save failed");
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
          message.info(t("memory.vs.loadStarted"));
        } else if (state?.status === "downloading") {
          message.info(t("memory.vs.downloadStarted"));
        }
      } else {
        message.success(t("memory.vs.applySuccess"));
      }
    } catch (err) {
      message.error(t("common.saveFailed") || "Save failed");
      console.error(err);
    } finally {
      setApplying(false);
    }
  }, [config, refreshDownloadStatus, t]);

  /** Disable vector search in one action by applying provider=none immediately. */
  const handleDisableVectorSearch = useCallback(() => {
    if (!config || config.provider === "none") return;
    modal.confirm({
      title: t("memory.vs.disableVectorConfirmTitle"),
      content: t("memory.vs.disableVectorConfirmDesc"),
      okText: t("common.disable"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      async onOk() {
        try {
          setApplying(true);
          const next = { ...config, provider: "none" as const };
          const updated = await api.applyConfig(next);
          setConfig(updated);
          message.success(t("memory.vs.disableVectorSuccess"));
          await refreshDownloadStatus();
        } catch (err) {
          message.error(t("common.saveFailed") || "Save failed");
          console.error(err);
        } finally {
          setApplying(false);
        }
      },
    });
  }, [config, refreshDownloadStatus, t]);

  // Download completion/failure notifications.
  // prevStatusRef prevents duplicate notifications after remounts.
  useEffect(() => {
    if (!downloadState) return;
    const prev = prevStatusRef.current;
    const curr = downloadState.status;
    prevStatusRef.current = curr;

    // Trigger only on status changes to done/failed to avoid repeated toasts.
    if (prev === curr) return;

    if (curr === "done") {
      // Persist downloaded model name.
      const modelName = downloadState.model_name || config?.localModel || "";
      if (modelName) {
        setDownloadedModels((prev) => {
          const next = prev.includes(modelName) ? prev : [...prev, modelName];
          localStorage.setItem("lc_downloaded_models", JSON.stringify(next));
          return next;
        });
      }
      if (prev === "loading") {
        message.success(t("memory.vs.loadComplete"));
      } else if (prev === "downloading") {
        message.success(t("memory.vs.downloadComplete"));
      }
    } else if (curr === "failed") {
      const fallbackMessage =
        prev === "loading"
          ? t("memory.vs.loadFailed")
          : t("memory.vs.downloadFailed");
      message.error(downloadState.error || fallbackMessage);
    }
  }, [downloadState, t, config?.localModel]);

  // Trigger model download.
  const handleDownloadModel = useCallback(async () => {
    try {
      await api.downloadLocalModel(config?.localModel || "");
      const state = await refreshDownloadStatus();
      if (state?.status === "loading") {
        message.info(t("memory.vs.loadStarted"));
      } else if (state?.status === "downloading") {
        message.info(t("memory.vs.downloadStarted"));
      }
    } catch (err) {
      message.error(t("memory.vs.downloadFailed"));
      console.error(err);
    }
  }, [config?.localModel, t, refreshDownloadStatus]);

  const handleDeleteModel = useCallback(async () => {
    const currentModel = config?.localModel || "";
    if (!currentModel) return;

    modal.confirm({
      title: t("memory.vs.deleteModelCacheTitle"),
      content: t("memory.vs.deleteModelCacheDesc", { model: currentModel }),
      okText: t("common.delete"),
      okType: "danger",
      cancelText: t("common.cancel"),
      async onOk() {
        try {
          await api.deleteLocalModel(currentModel);
          setDownloadedModels((prev) => {
            const next = prev.filter((m) => m !== currentModel);
            localStorage.setItem("lc_downloaded_models", JSON.stringify(next));
            return next;
          });
          message.success(t("memory.vs.deleteModelCacheSuccess"));
          await refreshDownloadStatus();
        } catch (err) {
          // 409: current model is being activated, so the backend refuses deletion.
          message.error(t("memory.vs.deleteModelCacheFailed"));
          console.error(err);
        }
      },
    });
  }, [config?.localModel, refreshDownloadStatus, t]);

  // Update a config field.
  const updateConfig = (field: keyof EmbeddingConfig, value: unknown) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  if (loading || !config) {
    return (
      <div className={styles.loading}>
        <Spin size="large" />
      </div>
    );
  }

  const currentModel = config.localModel;
  const isDownloaded = downloadedModels.includes(currentModel);
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
      ? t("memory.vs.modeLocal")
      : appliedProvider === "custom"
      ? t("memory.vs.modeCustom")
      : t("common.disabled");

  return (
    <div className={styles.page}>
      <div className={styles.intro}>
        <p className={styles.introDesc}>{t("memory.vs.description")}</p>
      </div>

      <Alert
        type="warning"
        showIcon
        message={t("memory.vs.vectorIndexWarning")}
        className={styles.vectorIndexAlert}
      />

      <div className={styles.appliedCard}>
        <div className={styles.appliedHeader}>
          <h3 className={styles.sectionTitle}>
            {t("memory.vs.currentApplied")}
          </h3>
          <span className={`${styles.statusBadge} ${styles[appliedStatus]}`}>
            {appliedStatus === "loading"
              ? t("memory.vs.loading")
              : appliedStatus === "downloading"
              ? t("memory.vs.downloading")
              : appliedStatus === "done"
              ? t("memory.vs.done")
              : appliedStatus === "failed"
              ? t("memory.vs.failed")
              : t("memory.vs.idle")}
          </span>
        </div>
        <div className={styles.appliedGrid}>
          <div className={styles.appliedItem}>
            <span className={styles.appliedLabel}>{t("memory.vs.engine")}</span>
            <span className={styles.appliedValue}>{appliedProviderLabel}</span>
          </div>
          <div className={styles.appliedItem}>
            <span className={styles.appliedLabel}>
              {t("memory.vs.modelName")}
            </span>
            <span className={styles.appliedValue}>{appliedModelName}</span>
          </div>
        </div>
      </div>

      {/* Search engine selection */}
      <div className={styles.card}>
        <div className={styles.engineHeader}>
          <h3 className={styles.sectionTitle}>{t("memory.vs.engine")}</h3>
          {config.provider !== "none" && (
            <Button
              danger
              type="default"
              onClick={handleDisableVectorSearch}
              disabled={saving || applying}
            >
              {t("memory.vs.disableVectorSearch")}
            </Button>
          )}
        </div>

        <div className={styles.radioGroup}>
          {/* Disabled */}
          <label
            className={`${styles.radioOption} ${
              config.provider === "none" ? styles.radioSelected : ""
            }`}
          >
            <input
              type="radio"
              name="vs-provider"
              value="none"
              checked={config.provider === "none"}
              onChange={() => updateConfig("provider", "none")}
            />
            <div className={styles.radioContent}>
              <span className={styles.radioLabel}>{t("common.disabled")}</span>
              <span className={styles.radioDesc}>
                {t("memory.vs.modeNoneDesc")}
              </span>
            </div>
          </label>

          {/* Local model */}
          <label
            className={`${styles.radioOption} ${
              config.provider === "local" ? styles.radioSelected : ""
            }`}
          >
            <input
              type="radio"
              name="vs-provider"
              value="local"
              checked={config.provider === "local"}
              onChange={() => updateConfig("provider", "local")}
            />
            <div className={styles.radioContent}>
              <span className={styles.radioLabel}>
                {t("memory.vs.modeLocal")}
              </span>
              <span className={styles.radioDesc}>
                {t("memory.vs.modeLocalDesc")}
              </span>
            </div>
          </label>

          {/* Third-party service */}
          <label
            className={`${styles.radioOption} ${
              config.provider === "custom" ? styles.radioSelected : ""
            }`}
          >
            <input
              type="radio"
              name="vs-provider"
              value="custom"
              checked={config.provider === "custom"}
              onChange={() => updateConfig("provider", "custom")}
            />
            <div className={styles.radioContent}>
              <span className={styles.radioLabel}>
                {t("memory.vs.modeCustom")}
              </span>
              <span className={styles.radioDesc}>
                {t("memory.vs.modeCustomDesc")}
              </span>
            </div>
          </label>
        </div>
      </div>

      {/* Local model config block */}
      {config.provider === "local" && (
        <div className={styles.card}>
          <h3 className={styles.sectionTitle}>{t("memory.vs.localConfig")}</h3>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("memory.vs.modelName")}</label>
            <Select
              value={config.localModel}
              onChange={(value) => updateConfig("localModel", value)}
              options={presetModels.map((model) => ({
                label: model,
                value: model,
              }))}
              placeholder={t("memory.vs.selectModel") || "Select a model"}
              className={styles.select}
            />
            <span className={styles.hint}>{t("memory.vs.modelNameHint")}</span>
          </div>

          {/* Download status */}
          {(() => {
            const currentModel = config?.localModel || "";
            const isDownloaded = downloadedModels.includes(currentModel);
            const isActiveDownload =
              !!downloadState?.model_name &&
              downloadState.model_name === currentModel;
            if (
              downloadState &&
              downloadState.status === "loading" &&
              isActiveDownload
            ) {
              return (
                <div className={styles.downloadStatus}>
                  <div className={styles.statusHeader}>
                    <span className={styles.statusLabel}>
                      {t("memory.vs.downloadStatus")}
                    </span>
                    <span className={`${styles.statusBadge} ${styles.loading}`}>
                      {t("memory.vs.loading")}
                    </span>
                  </div>
                  <div className={styles.statusSuccess}>
                    <Spin size="small" />
                    <span>{t("memory.vs.loadStarted")}</span>
                  </div>
                </div>
              );
            }
            // Active download: prefer showing progress.
            if (
              downloadState &&
              downloadState.status === "downloading" &&
              isActiveDownload
            ) {
              return (
                <div className={styles.downloadStatus}>
                  <div className={styles.statusHeader}>
                    <span className={styles.statusLabel}>
                      {t("memory.vs.downloadStatus")}
                    </span>
                    <span
                      className={`${styles.statusBadge} ${styles.downloading}`}
                    >
                      {t("memory.vs.downloading")}
                    </span>
                  </div>
                  <div className={styles.progressBar}>
                    <Progress
                      percent={Math.round(downloadState.progress * 100)}
                      status="active"
                    />
                  </div>
                  <div className={styles.downloadMeta}>
                    <span>
                      {t("memory.vs.downloaded")}:{" "}
                      {getDownloadTransferred(downloadState)}
                    </span>
                    <span>
                      {t("memory.vs.speed")}: {getDownloadSpeed(downloadState)}
                    </span>
                    <span>
                      {t("memory.vs.elapsed")}:{" "}
                      {formatDuration(downloadState.elapsed_seconds)}
                    </span>
                    <span>
                      {t("memory.vs.remaining")}:{" "}
                      {formatDuration(downloadState.eta_seconds)}
                    </span>
                  </div>
                </div>
              );
            }
            // Download failed.
            if (
              downloadState &&
              downloadState.status === "failed" &&
              isActiveDownload
            ) {
              return (
                <div className={styles.downloadStatus}>
                  <div className={styles.statusHeader}>
                    <span className={styles.statusLabel}>
                      {t("memory.vs.downloadStatus")}
                    </span>
                    <span className={`${styles.statusBadge} ${styles.failed}`}>
                      {t("memory.vs.failed")}
                    </span>
                  </div>
                  <div className={styles.statusError}>
                    <AlertCircle size={15} />
                    <span>
                      {downloadState.error || t("memory.vs.downloadFailed")}
                    </span>
                  </div>
                </div>
              );
            }
            // Ready: backend reports done or localStorage records it as downloaded.
            const isReady =
              (downloadState &&
                downloadState.status === "done" &&
                isActiveDownload) ||
              isDownloaded;
            if (isReady) {
              return (
                <div className={styles.downloadStatus}>
                  <div className={styles.statusHeader}>
                    <span className={styles.statusLabel}>
                      {t("memory.vs.downloadStatus")}
                    </span>
                    <span className={`${styles.statusBadge} ${styles.done}`}>
                      {t("memory.vs.done")}
                    </span>
                  </div>
                  <div className={styles.statusSuccess}>
                    <CheckCircle size={15} />
                    <span>{t("memory.vs.ready")}</span>
                  </div>
                </div>
              );
            }
            // Not downloaded.
            return (
              <div className={styles.downloadStatus}>
                <div className={styles.statusHeader}>
                  <span className={styles.statusLabel}>
                    {t("memory.vs.downloadStatus")}
                  </span>
                  <span className={`${styles.statusBadge} ${styles.idle}`}>
                    {t("memory.vs.idle")}
                  </span>
                </div>
                <p className={styles.hint}>
                  {t("memory.vs.notDownloadedHint")}
                </p>
              </div>
            );
          })()}

          <Button
            icon={<Download size={15} />}
            onClick={handleDownloadModel}
            loading={isStatusBusy}
            disabled={isStatusBusy}
            className={styles.downloadBtn}
          >
            {t("memory.vs.downloadModel")}
          </Button>

          {isDownloaded && (
            <Button
              danger
              onClick={handleDeleteModel}
              disabled={isStatusBusy}
              className={styles.deleteBtn}
              style={{ marginTop: 12 }}
            >
              {t("memory.vs.deleteModelBtn")}
            </Button>
          )}
        </div>
      )}
      {/* Third-party service config block */}
      {config.provider === "custom" && (
        <div className={styles.card}>
          <h3 className={styles.sectionTitle}>{t("memory.vs.customConfig")}</h3>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("memory.vs.apiKey")}</label>
            <Input.Password
              value={config.apiKey}
              onChange={(e) => updateConfig("apiKey", e.target.value)}
              placeholder="sk-..."
              className={styles.input}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("memory.vs.baseUrl")}</label>
            <Input
              value={config.baseUrl}
              onChange={(e) => updateConfig("baseUrl", e.target.value)}
              placeholder="https://api.openai.com/v1"
              className={styles.input}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>
              {t("memory.vs.modelNameLabel")}
            </label>
            <Input
              value={config.modelName}
              onChange={(e) => updateConfig("modelName", e.target.value)}
              placeholder="text-embedding-3-small"
              className={styles.input}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>{t("memory.vs.dimensions")}</label>
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

      {/* Save buttons */}
      <div className={styles.actions}>
        <Button onClick={handleSaveConfig} loading={saving} disabled={applying}>
          {t("common.save")}
        </Button>
        <Button
          type="primary"
          onClick={handleApplyConfig}
          loading={applying}
          disabled={saving}
        >
          {t("memory.vs.saveAndApply")}
        </Button>
      </div>
    </div>
  );
}
