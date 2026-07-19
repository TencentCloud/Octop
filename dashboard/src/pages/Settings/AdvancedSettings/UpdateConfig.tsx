import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Collapse } from "antd";
import {
  CheckCircle,
  RefreshCw,
  XCircle,
  AlertTriangle,
  Power,
} from "lucide-react";
import {
  updateApi,
  UpdateStatus,
  UpgradeProgress,
} from "../../../api/modules/update";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import { useServiceRestartContext } from "../../../context/ServiceRestartContext";
import {
  clearStoredUpdateStatus,
  storeUpdateStatus,
} from "../../../utils/updateStatusCache";
import styles from "./UpdateConfig.module.less";

export default function UpdateConfig() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [upgrading, setUpgrading] = useState(false);
  const [progress, setProgress] = useState<UpgradeProgress | null>(null);
  const { restartPhase, isRestarting, requestRestart } =
    useServiceRestartContext();
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    updateApi
      .getUpdateStatus()
      .then((next) => {
        storeUpdateStatus(next);
        setStatus(next);
      })
      .catch(() => {});
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, []);

  const handleCheck = useCallback(async () => {
    setChecking(true);
    try {
      const result = await updateApi.checkForUpdates();
      storeUpdateStatus(result);
      setStatus(result);
    } catch {
      // network error – keep existing status
    } finally {
      setChecking(false);
    }
  }, []);

  const pollProgress = useCallback(async (taskId: string) => {
    try {
      const prog = await updateApi.getUpgradeProgress(taskId);
      setProgress(prog);
      if (prog.status === "running") {
        pollTimerRef.current = setTimeout(() => pollProgress(taskId), 800);
      } else {
        setUpgrading(false);
        if (prog.status === "complete") {
          clearStoredUpdateStatus();
          updateApi
            .getUpdateStatus()
            .then((next) => {
              storeUpdateStatus(next);
              setStatus(next);
            })
            .catch(() => {});
        }
      }
    } catch {
      setUpgrading(false);
    }
  }, []);

  const handleUpgrade = useCallback(async () => {
    setUpgrading(true);
    setProgress(null);
    try {
      const started = await updateApi.triggerUpgrade();
      setProgress({
        task_id: started.task_id,
        status: "running",
        stage: "starting",
        percent: 0,
        new_version: null,
        success: null,
        error: null,
        mirror_errors: null,
      });
      pollProgress(started.task_id);
    } catch (err: unknown) {
      setUpgrading(false);
      const msg = err instanceof Error ? err.message : String(err);
      setProgress({
        task_id: "",
        status: "error",
        stage: null,
        percent: null,
        new_version: null,
        success: false,
        error: msg,
        mirror_errors: null,
      });
    }
  }, [pollProgress]);

  const stageLabel = (stage: string | null) => {
    switch (stage) {
      case "starting":
        return t("advancedSettings.update.stageStarting");
      case "downloading":
        return t("advancedSettings.update.stageDownloading");
      case "installing":
        return t("advancedSettings.update.stageInstalling");
      default:
        return t("advancedSettings.update.upgrading");
    }
  };

  const upgradeFinished =
    progress && (progress.status === "complete" || progress.status === "error");
  const isServiceMode = !!status?.service_mode;
  const restartUiLocked = restartPhase !== "idle" && restartPhase !== "timeout";

  return (
    <div className={styles.container}>
      <p className={styles.description}>
        {t("advancedSettings.update.description")}
      </p>

      {/* Version info cards */}
      <div className={styles.versionGrid}>
        <div className={styles.versionCard}>
          <span className={styles.versionLabel}>
            {t("advancedSettings.update.currentVersion")}
          </span>
          <span className={styles.versionValue}>
            {status?.current_version ?? "—"}
          </span>
        </div>
        <div className={styles.versionCard}>
          <span className={styles.versionLabel}>
            {t("advancedSettings.update.latestVersion")}
          </span>
          <span className={styles.versionValue}>
            {status?.latest_version ?? (
              <span className={styles.notChecked}>
                {t("advancedSettings.update.notChecked")}
              </span>
            )}
          </span>
          {status?.has_update && (
            <span className={styles.badge}>
              {t("advancedSettings.update.updateAvailable")}
            </span>
          )}
        </div>
      </div>

      {/* Release notes collapse — only shown when an update is available and notes exist */}
      {status?.has_update && status.release_notes && (
        <Collapse
          defaultActiveKey={["changelog"]}
          style={{ marginBottom: 12 }}
          items={[
            {
              key: "changelog",
              label: t("advancedSettings.update.releaseNotes"),
              children: (
                <div style={{ maxHeight: 300, overflowY: "auto" }}>
                  <Markdown content={status.release_notes} />
                </div>
              ),
            },
          ]}
        />
      )}

      {/* Editable install warning */}
      {status?.is_editable && (
        <div className={`${styles.alert} ${styles.alertWarn}`}>
          <AlertTriangle size={15} />
          <span>{t("advancedSettings.update.editableHint")}</span>
        </div>
      )}

      {/* Network error */}
      {status?.error && (
        <div className={`${styles.alert} ${styles.alertError}`}>
          <XCircle size={15} />
          <span>{status.error}</span>
        </div>
      )}

      {/* Action buttons */}
      <div className={styles.actions}>
        <button
          className={styles.btnSecondary}
          onClick={handleCheck}
          disabled={checking || upgrading || restartUiLocked}
        >
          <RefreshCw
            size={14}
            className={checking ? styles.spinning : undefined}
          />
          {checking
            ? t("advancedSettings.update.checking")
            : t("advancedSettings.update.checkButton")}
        </button>

        {isServiceMode && (
          <button
            className={styles.btnSecondary}
            onClick={requestRestart}
            disabled={checking || upgrading || restartUiLocked}
          >
            <Power size={14} />
            {isRestarting
              ? t("advancedSettings.update.restarting")
              : t("advancedSettings.update.restartServiceBtn")}
          </button>
        )}

        {status?.has_update && !status.is_editable && !upgradeFinished && (
          <button
            className={styles.btnPrimary}
            onClick={handleUpgrade}
            disabled={upgrading}
          >
            {upgrading
              ? t("advancedSettings.update.upgrading")
              : t("advancedSettings.update.upgradeButton")}
          </button>
        )}
      </div>

      {/* Upgrade progress */}
      {progress && (
        <div className={styles.progressSection}>
          {progress.status === "running" && (
            <>
              <div className={styles.progressLabel}>
                <RefreshCw size={13} className={styles.spinning} />
                <span>{stageLabel(progress.stage)}</span>
              </div>
              <div className={styles.progressBar}>
                <div
                  className={styles.progressFill}
                  style={{ width: `${progress.percent ?? 10}%` }}
                />
              </div>
            </>
          )}

          {progress.status === "complete" && (
            <>
              <div className={`${styles.alert} ${styles.alertSuccess}`}>
                <CheckCircle size={15} />
                <span>
                  {t("advancedSettings.update.upgradeSuccess")}
                  {progress.new_version && ` → v${progress.new_version}`}
                </span>
              </div>

              {/* Restart section */}
              {restartPhase === "idle" &&
                (isServiceMode ? (
                  <div className={`${styles.alert} ${styles.alertInfo}`}>
                    <AlertTriangle size={15} />
                    <div className={styles.restartRow}>
                      <p>{t("advancedSettings.update.restartHint")}</p>
                      <button
                        className={styles.btnPrimary}
                        onClick={requestRestart}
                      >
                        <Power size={14} />
                        {t("advancedSettings.update.restartServiceBtn")}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className={`${styles.alert} ${styles.alertInfo}`}>
                    <AlertTriangle size={15} />
                    <div>
                      <p>{t("advancedSettings.update.restartHint")}</p>
                      <div className={styles.commandBlock}>
                        <code>octop restart</code>
                        <span className={styles.commandSep}>/</span>
                        <code>octop run</code>
                      </div>
                    </div>
                  </div>
                ))}
            </>
          )}

          {progress.status === "error" && (
            <div className={`${styles.alert} ${styles.alertError}`}>
              <XCircle size={15} />
              <div>
                <p>
                  {t("advancedSettings.update.upgradeFailed")}: {progress.error}
                </p>
                <p className={styles.manualHint}>
                  {t("advancedSettings.update.manualUpgradeHint")}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
