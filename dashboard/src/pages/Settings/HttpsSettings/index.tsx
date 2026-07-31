import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Input,
  Space,
  Spin,
  Steps,
  Switch,
  Table,
  Typography,
} from "antd";
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
import updateStyles from "../AdvancedSettings/UpdateConfig.module.less";
import tabStyles from "../AdvancedSettings/tabContent.module.less";

const { Text } = Typography;

const TASK_STEP_ORDER = [
  "idle",
  "preflight",
  "challenging",
  "issuing",
  "installing",
  "restart_required",
  "active",
] as const;

function taskStepIndex(state: string): number {
  const idx = TASK_STEP_ORDER.indexOf(
    state as (typeof TASK_STEP_ORDER)[number],
  );
  return idx >= 0 ? idx : 0;
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
        row.ok ? t("tls.pass") : t("tls.fail"),
    },
    {
      title: t("tls.checkMessage"),
      dataIndex: "message",
      key: "message",
    },
  ];

  return (
    <>
      <TabPanelHeader
        icon={<Lock size={22} />}
        title={t("tls.title")}
        description={t("tls.subtitle")}
      />

      {loading && !status ? (
        <Spin />
      ) : (
        <>
          {tlsEnabled && status?.tls.expires_at && (
            <Alert
              type="success"
              showIcon
              icon={<ShieldCheck size={16} />}
              message={t("tls.activeCert", {
                expires: status.tls.expires_at,
                httpPort: status.tls.http_port,
              })}
              style={{ marginBottom: 16 }}
            />
          )}

          {taskState === "restart_required" && (
            <Alert
              type="warning"
              showIcon
              message={t("tls.restartRequired")}
              description={
                serviceMode ? (
                  <div
                    className={updateStyles.restartRow}
                    style={{ marginTop: 8 }}
                  >
                    <p>{t("tls.restartRequiredHint")}</p>
                    <Button
                      type="primary"
                      icon={<Power size={14} />}
                      onClick={requestRestart}
                      disabled={
                        restartPhase !== "idle" && restartPhase !== "timeout"
                      }
                    >
                      {t("advancedSettings.update.restartServiceBtn")}
                    </Button>
                  </div>
                ) : (
                  <div style={{ marginTop: 8 }}>
                    <p style={{ margin: "0 0 8px" }}>
                      {t("tls.restartRequiredHint")}
                    </p>
                    <div className={updateStyles.commandBlock}>
                      <code>octop restart</code>
                      <span className={updateStyles.commandSep}>/</span>
                      <code>octop run</code>
                    </div>
                  </div>
                )
              }
              style={{ marginBottom: 16 }}
            />
          )}

          {taskState === "failed" && status?.task.error && (
            <Alert
              type="error"
              message={status.task.error}
              style={{ marginBottom: 16 }}
            />
          )}

          {!eligible && !tlsEnabled && (
            <Alert
              type="info"
              message={t("tls.notEligible")}
              style={{ marginBottom: 16 }}
            />
          )}

          {status?.tls.dual_listeners && (
            <Alert
              type="info"
              message={t("tls.dualPortActive", {
                httpPort: status.tls.http_port,
                httpsPort: status.tls.https_port ?? 443,
              })}
              style={{ marginBottom: 16 }}
            />
          )}

          <Steps
            current={taskStepIndex(taskState)}
            size="small"
            style={{ marginBottom: 24 }}
            items={[
              { title: t("tls.stepPreflight") },
              { title: t("tls.stepChallenge") },
              { title: t("tls.stepIssue") },
              { title: t("tls.stepInstall") },
              { title: t("tls.stepRestart") },
              { title: t("tls.stepActive") },
            ]}
          />

          <div className={tabStyles.formFieldsWide}>
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <div>
                <Text strong>{t("tls.domainLabel")}</Text>
                <Input
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  placeholder={t("tls.domainPlaceholder")}
                  disabled={formLocked}
                  style={{ marginTop: 8 }}
                />
              </div>

              <Space wrap>
                <Switch
                  checked={staging}
                  onChange={setStaging}
                  disabled={formLocked}
                />
                <Text type="secondary">{t("tls.stagingHint")}</Text>
              </Space>

              <Space wrap>
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
              </Space>

              {checks.length > 0 && (
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  columns={checkColumns}
                  dataSource={checks}
                />
              )}
            </Space>
          </div>
        </>
      )}
    </>
  );
}
