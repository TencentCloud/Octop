import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Input, Spin, Steps, Switch, Table } from "antd";
import { message } from "@/utils/antdMessage";

import { Lock, Power, RefreshCw, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  tlsApi,
  type PreflightCheck,
  type TlsStatus,
} from "../../../api/modules/tls";
import { updateApi } from "../../../api/modules/update";
import { useServiceRestartContext } from "../../../context/ServiceRestartContext";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

const TASK_STEP_ORDER = [
  "idle",
  "preflight",
  "challenging",
  "issuing",
  "installing",
  "restart_required",
  "active",
] as const;

/** Map task state → Steps `current` index (items omit idle). */
function stepsCurrent(state: string): number {
  const idx = TASK_STEP_ORDER.indexOf(
    state as (typeof TASK_STEP_ORDER)[number],
  );
  if (idx <= 0) return 0;
  // active (last in order) should highlight final step
  return Math.min(idx - 1, 5);
}

function stepsStatus(state: string): "wait" | "process" | "finish" | "error" {
  if (state === "failed") return "error";
  if (state === "active") return "finish";
  if (["preflight", "challenging", "issuing", "installing"].includes(state)) {
    return "process";
  }
  return "wait";
}

export function HttpsSettingsPanel() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<TlsStatus | null>(null);
  const [domain, setDomain] = useState("");
  const [staging, setStaging] = useState(false);
  const [checks, setChecks] = useState<PreflightCheck[]>([]);
  const [preflightOk, setPreflightOk] = useState(false);
  const [checking, setChecking] = useState(false);
  const [issuing, setIssuing] = useState(false);
  const [serviceMode, setServiceMode] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const domainInitialized = useRef(false);
  const { restartPhase, requestRestart } = useServiceRestartContext();

  const fetchStatus = useCallback(async () => {
    try {
      const s = await tlsApi.getStatus();
      setStatus(s);
      if (!domainInitialized.current && s.tls.domains[0]) {
        setDomain(s.tls.domains[0]);
        domainInitialized.current = true;
      }
      return s;
    } catch (err) {
      message.error(t("tls.loadError"));
      console.error(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchStatus();
    updateApi
      .getUpdateStatus()
      .then((s) => setServiceMode(s.service_mode ?? null))
      .catch(() => setServiceMode(null));
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startPolling = () => {
    stopPolling();
    pollRef.current = setInterval(() => {
      void fetchStatus();
    }, 2000);
  };

  const handlePreflight = async () => {
    const d = domain.trim();
    if (!d) {
      message.warning(t("tls.domainRequired"));
      return;
    }
    setChecking(true);
    try {
      const result = await tlsApi.preflight(d);
      setChecks(result.checks);
      setPreflightOk(result.ok);
      if (result.ok) {
        message.success(t("tls.preflightOk"));
      } else {
        message.error(t("tls.preflightFailed"));
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("tls.preflightFailed"),
      );
    } finally {
      setChecking(false);
    }
  };

  const handleIssue = async () => {
    const d = domain.trim();
    if (!d) {
      message.warning(t("tls.domainRequired"));
      return;
    }
    setIssuing(true);
    try {
      const result = await tlsApi.issue(d, staging);
      setChecks(result.checks);
      setPreflightOk(result.ok);
      if (!result.ok) {
        message.error(t("tls.preflightFailed"));
        return;
      }
      message.info(t("tls.issueStarted"));
      startPolling();
      await fetchStatus();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("tls.issueFailed"));
    } finally {
      setIssuing(false);
    }
  };

  useEffect(() => {
    const state = status?.task.state;
    if (
      state === "restart_required" ||
      state === "active" ||
      state === "failed" ||
      state === "idle"
    ) {
      stopPolling();
    }
  }, [status?.task.state]);

  const eligible = status?.eligible ?? false;
  const renewal = Boolean(status?.renewal);
  const taskState = status?.task.state ?? "idle";
  const tlsEnabled = status?.tls.enabled ?? false;
  const busy = ["preflight", "challenging", "issuing", "installing"].includes(
    taskState,
  );
  const formLocked = busy || (tlsEnabled && !renewal);

  const checkColumns = [
    {
      title: t("tls.checkItem"),
      dataIndex: "id",
      key: "id",
      width: 140,
    },
    {
      title: t("tls.checkResult"),
      key: "ok",
      width: 100,
      render: (_: unknown, row: PreflightCheck) =>
        row.ok ? (
          <span className={styles.pass}>{t("tls.pass")}</span>
        ) : (
          <span className={styles.fail}>{t("tls.fail")}</span>
        ),
    },
    {
      title: t("tls.checkMessage"),
      dataIndex: "message",
      key: "message",
    },
  ];

  return (
    <div className={styles.container}>
      <TabPanelHeader
        icon={<Lock size={22} />}
        title={t("tls.title")}
        description={t("tls.subtitle")}
      />

      {loading && !status ? (
        <div className={styles.loading}>
          <Spin />
        </div>
      ) : (
        <>
          <div className={styles.statusStack}>
            {tlsEnabled && status?.tls.expires_at && (
              <Alert
                type="success"
                showIcon
                icon={<ShieldCheck size={16} />}
                message={t("tls.activeCert", {
                  expires: status.tls.expires_at,
                  httpPort: status.tls.http_port,
                })}
              />
            )}

            {taskState === "restart_required" && (
              <Alert
                type="warning"
                showIcon
                message={t("tls.restartRequired")}
                description={
                  serviceMode ? (
                    <div className={styles.restartBlock}>
                      <p>{t("tls.restartRequiredHint")}</p>
                      <span>
                        <Button
                          type="primary"
                          icon={<Power size={14} />}
                          onClick={requestRestart}
                          disabled={
                            restartPhase !== "idle" &&
                            restartPhase !== "timeout"
                          }
                        >
                          {t("advancedSettings.update.restartServiceBtn")}
                        </Button>
                      </span>
                    </div>
                  ) : (
                    <div className={styles.restartBlock}>
                      <p>{t("tls.restartRequiredHint")}</p>
                      <div className={styles.commandBlock}>
                        <code>octop service restart</code>
                        <span className={styles.commandSep}>/</span>
                        <code>octop run</code>
                      </div>
                    </div>
                  )
                }
              />
            )}

            {taskState === "failed" && status?.task.error && (
              <Alert type="error" showIcon message={status.task.error} />
            )}

            {!eligible && !tlsEnabled && (
              <Alert type="info" showIcon message={t("tls.notEligible")} />
            )}

            {status?.tls.dual_listeners && (
              <Alert
                type="info"
                showIcon
                message={t("tls.dualPortActive", {
                  httpPort: status.tls.http_port,
                  httpsPort: status.tls.https_port ?? 443,
                })}
              />
            )}
          </div>

          <div className={styles.panel}>
            <Steps
              className={styles.steps}
              current={stepsCurrent(taskState)}
              status={stepsStatus(taskState)}
              size="small"
              items={[
                { title: t("tls.stepPreflight") },
                { title: t("tls.stepChallenge") },
                { title: t("tls.stepIssue") },
                { title: t("tls.stepInstall") },
                { title: t("tls.stepRestart") },
                { title: t("tls.stepActive") },
              ]}
            />

            <div className={styles.field}>
              <p className={styles.fieldLabel}>{t("tls.domainLabel")}</p>
              <Input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder={t("tls.domainPlaceholder")}
                disabled={formLocked}
              />
            </div>

            <div className={styles.stagingRow}>
              <Switch
                checked={staging}
                onChange={setStaging}
                disabled={formLocked}
              />
              <p className={styles.stagingText}>{t("tls.stagingHint")}</p>
            </div>

            <div className={styles.actions}>
              <Button
                onClick={() => void handlePreflight()}
                loading={checking}
                disabled={formLocked}
              >
                {t("tls.runPreflight")}
              </Button>
              <Button
                type="primary"
                onClick={() => void handleIssue()}
                loading={issuing || busy}
                disabled={!eligible || (!preflightOk && checks.length > 0)}
              >
                {renewal ? t("tls.renewCert") : t("tls.startIssue")}
              </Button>
              <Button
                icon={<RefreshCw size={14} />}
                onClick={() => void fetchStatus()}
              >
                {t("tls.refresh")}
              </Button>
            </div>

            {checks.length > 0 && (
              <div className={styles.checks}>
                <p className={styles.checksTitle}>{t("tls.checksTitle")}</p>
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  columns={checkColumns}
                  dataSource={checks}
                />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
