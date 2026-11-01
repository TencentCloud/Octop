import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, App, Button } from "antd";
import { Copy, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  decisionApi,
  type LayaPhase,
  type LayaStatus,
} from "../../../../api/modules/decision";
import { copyText } from "../../../../utils/copyText";
import { apiErrorMessage } from "../../../../utils/apiError";
import styles from "./DecisionSettingsPanel.module.less";

const EMPTY: LayaStatus = {
  installed: false,
  running: false,
  managed: false,
  phase: "missing",
  endpoint: "",
  port: 8000,
  command: "",
  logs: [],
};

export function LayaLocalInstall({
  active,
  onReady,
  onStatusChange,
}: {
  active: boolean;
  onReady: () => void;
  onStatusChange: (status: LayaStatus) => void;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [status, setStatus] = useState<LayaStatus>(EMPTY);
  const [logs, setLogs] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);
  const installRef = useRef<AbortController | null>(null);

  const apply = useCallback(
    (next: LayaStatus) => {
      setStatus(next);
      onStatusChange(next);
      if (next.logs.length > 0) setLogs(next.logs);
    },
    [onStatusChange],
  );

  useEffect(() => {
    let cancelled = false;
    void decisionApi
      .layaStatus()
      .then((next) => {
        if (cancelled) return;
        apply(next);
        if (next.phase === "installing") startInstall();
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      installRef.current?.abort();
    };
    // Attach once when the Laya drawer opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status.phase !== "starting") return undefined;
    const timer = window.setInterval(() => {
      void decisionApi
        .layaStatus()
        .then(apply)
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [apply, status.phase]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  const startInstall = () => {
    if (installRef.current) return;
    setStatus((prev) => ({ ...prev, phase: "installing" }));
    setLogs([]);
    installRef.current = decisionApi.installLaya(
      (line) => setLogs((prev) => [...prev, line]),
      (success) => {
        installRef.current = null;
        void decisionApi
          .layaStatus()
          .then((next) => {
            apply(next);
            if (success) {
              onReady();
              message.success(t("models.decisionLayaReadyHint"));
            }
          })
          .catch(() => {
            setStatus((prev) => ({
              ...prev,
              phase: success ? "running" : "failed",
            }));
          });
      },
    );
  };

  const phaseLabel: Record<LayaPhase, string> = {
    missing: t("models.decisionLayaMissing"),
    installing: t("models.decisionLayaInstalling"),
    starting: t("models.decisionLayaStarting"),
    running: t("models.decisionLayaRunning"),
    stopped: t("models.decisionLayaStopped"),
    failed: t("models.decisionLayaFailed"),
  };

  const copyLog = async () => {
    const body =
      logs.length > 0 ? logs.join("\n") : t("common.installLogEmpty");
    const command = status.command ? `\n${status.command}\n` : "";
    const payload = `${t("models.decisionLayaFailed")}\n${t(
      "models.decisionLayaFailGuide",
    )}\n${command}\n${body}`;
    const ok = await copyText(payload);
    if (ok) message.success(t("common.copied"));
    else message.error(t("common.copyFailed"));
  };

  const copyCommand = async () => {
    if (!status.command) return;
    const ok = await copyText(status.command);
    if (ok) message.success(t("common.copied"));
    else message.error(t("common.copyFailed"));
  };

  const run = async (action: "start" | "stop") => {
    setBusy(true);
    try {
      const next =
        action === "start"
          ? await decisionApi.startLaya()
          : await decisionApi.stopLaya();
      apply(next);
    } catch (error) {
      message.error(apiErrorMessage(error, t("common.saveFailed"), t));
    } finally {
      setBusy(false);
    }
  };

  const showLog =
    status.phase === "installing" ||
    status.phase === "starting" ||
    status.phase === "failed" ||
    logs.length > 0;
  const external = status.running && !status.managed;

  return (
    <div className={styles.installCard}>
      <div className={styles.installHead}>
        <span className={styles.configSectionTitle}>
          {t("models.decisionLayaInstallTitle")}
        </span>
        <span className={styles.installPhase}>{phaseLabel[status.phase]}</span>
      </div>
      <p className={styles.installDesc}>
        {t("models.decisionLayaInstallDesc")}
      </p>
      <div className={styles.serviceStatus}>
        <span
          className={`${styles.serviceStatusItem} ${
            status.running ? styles.serviceStatusReady : ""
          }`}
        >
          <span className={styles.serviceStatusDot} />
          {status.running
            ? t("models.decisionServiceReady")
            : t("models.decisionServiceNotReady")}
        </span>
        <span
          className={`${styles.serviceStatusItem} ${
            active ? styles.serviceStatusActive : ""
          }`}
        >
          <span className={styles.serviceStatusDot} />
          {active
            ? t("models.decisionDefaultActive")
            : t("models.decisionDefaultInactive")}
        </span>
      </div>
      {status.command ? (
        <div>
          <div className={styles.installHead}>
            <span className={styles.installPhase}>
              {t("models.decisionLayaCommand")}
            </span>
            <Button
              size="small"
              icon={<Copy size={14} />}
              onClick={() => void copyCommand()}
            >
              {t("models.decisionLayaCopyCommand")}
            </Button>
          </div>
          <pre className={styles.installCommand}>{status.command}</pre>
        </div>
      ) : null}
      {external ? (
        <Alert
          type="info"
          showIcon
          message={t("models.decisionLayaExternal")}
        />
      ) : null}
      {(status.phase === "installing" || status.phase === "starting") && (
        <div className={styles.installProgressTitle}>
          <RefreshCw size={14} className={styles.installSpin} />
          {phaseLabel[status.phase]}
        </div>
      )}
      {showLog ? (
        <div ref={logRef} className={styles.installLog}>
          {logs.length === 0 ? (
            <div>{t("models.decisionLayaInstalling")}</div>
          ) : (
            logs.map((line, index) => (
              <div key={`${index}-${line}`}>{line}</div>
            ))
          )}
        </div>
      ) : null}
      {status.phase === "failed" ? (
        <Alert
          type="error"
          showIcon
          message={t("models.decisionLayaFailed")}
          description={t("models.decisionLayaFailGuide")}
        />
      ) : null}
      <div className={styles.installActions}>
        {external ? (
          <Button type="primary" onClick={onReady}>
            {t("models.decisionLayaUseLocal")}
          </Button>
        ) : null}
        {!external &&
        (status.phase === "missing" || status.phase === "failed") ? (
          <Button type="primary" onClick={startInstall}>
            {status.phase === "failed"
              ? t("models.decisionLayaInstallRetry")
              : t("models.decisionLayaInstall")}
          </Button>
        ) : null}
        {!external && status.phase === "stopped" ? (
          <>
            <Button
              type="primary"
              loading={busy}
              onClick={() => void run("start")}
            >
              {t("models.decisionLayaStart")}
            </Button>
            <Button onClick={startInstall}>
              {t("models.decisionLayaInstallRetry")}
            </Button>
          </>
        ) : null}
        {status.managed && status.phase === "running" ? (
          <Button loading={busy} onClick={() => void run("stop")}>
            {t("models.decisionLayaStop")}
          </Button>
        ) : null}
        {status.phase === "failed" ? (
          <Button icon={<Copy size={14} />} onClick={() => void copyLog()}>
            {t("common.copyErrorForOctop")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
