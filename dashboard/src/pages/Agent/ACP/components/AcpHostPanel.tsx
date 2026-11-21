import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Segmented, Spin, Typography } from "antd";
import { message } from "@/utils/antdMessage";
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Download,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  acpApi,
  type AcpHostRequest,
  type AcpHostStatus,
} from "../../../../api/modules/acp";
import { parseArgsText, parseEnvText } from "../../../../api/types/acp";
import { copyText } from "../../../../utils/copyText";
import { AcpSectionToggle } from "./AcpSectionToggle";
import styles from "../index.module.less";

const PLATFORMS = ["linux", "darwin", "win32"] as const;

export function AcpHostPanel({
  open,
  runner,
  command,
  argsText,
  envText,
}: {
  open: boolean;
  runner: string;
  command: string;
  argsText: string;
  envText: string;
}) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [env, setEnv] = useState<AcpHostStatus | null>(null);
  const [platform, setPlatform] = useState("linux");
  const [installOpen, setInstallOpen] = useState(false);
  const connectedRef = useRef<boolean | null>(null);
  const latest = useRef({ command, argsText, envText, runner });
  latest.current = { command, argsText, envText, runner };

  const body = useCallback((): AcpHostRequest => {
    const current = latest.current;
    return {
      runner: current.runner,
      command: current.command.trim(),
      args: parseArgsText(current.argsText),
      env: parseEnvText(current.envText),
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!latest.current.runner && !latest.current.command.trim()) return;
    setLoading(true);
    try {
      const result = await acpApi.probeHost(body());
      setEnv(result);
      setPlatform(result.platform || "linux");
    } catch (err) {
      setEnv({
        runner: latest.current.runner,
        platform: "",
        command: latest.current.command,
        args: [],
        binary_found: false,
        acp_ok: false,
        install_script: "",
        scripts: {},
        agent_prompt: "",
        can_auto_install: false,
        status: "degraded",
        reason: "handshake_failed",
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setLoading(false);
    }
  }, [body]);

  useEffect(() => {
    if (!open) return;
    connectedRef.current = null;
    void refresh();
  }, [open, runner, refresh]);

  useEffect(() => {
    if (!env) return;
    const connected = env.status === "ready" || env.status === "installed";
    if (connectedRef.current === connected) return;
    connectedRef.current = connected;
    setInstallOpen(!connected);
  }, [env]);

  const applyResult = (result: AcpHostStatus) => {
    setEnv(result);
    if (result.platform) setPlatform(result.platform);
    if (result.status === "ready" || result.status === "installed") {
      message.success(t(`acp.host.status.${result.status}`));
    } else if (result.status === "skipped") {
      message.info(t("acp.host.status.skipped"));
    } else {
      message.warning(t(`acp.host.status.${result.status}`));
    }
  };

  const handleInstall = async () => {
    setBusy(true);
    try {
      applyResult(await acpApi.installHost(body()));
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const copyValue = async (text: string, okKey: string) => {
    if (!text) return;
    if (await copyText(text)) message.success(t(okKey));
    else message.error(t("acp.host.copyFailed"));
  };

  const status = env?.status ?? "missing";
  const ok = status === "ready" || status === "installed";
  const StatusIcon = ok ? CheckCircle2 : AlertCircle;
  const scripts = env?.scripts ?? {};
  const scriptPlatforms = PLATFORMS.filter((item) => scripts[item]);
  const selectedScript = scripts[platform] || env?.install_script || "";
  const hostScript = env?.install_script || "";
  const reasonKey = `acp.host.reason.${env?.reason ?? ""}`;
  const statusText = env
    ? t(reasonKey, { defaultValue: t(`acp.host.status.${status}`) })
    : t("acp.host.checking");

  return (
    <div className={styles.hostPanel}>
      <div className={styles.hostTitle}>{t("acp.host.title")}</div>
      {loading && !env ? (
        <div className={styles.hostStatus}>
          <Spin size="small" />
          <span>{t("acp.host.checking")}</span>
        </div>
      ) : (
        <div className={styles.hostStatus}>
          <StatusIcon
            size={16}
            className={ok ? styles.hostOk : styles.hostWarn}
            aria-hidden
          />
          <span>
            {statusText}
            {env?.detail ? (
              <span className={styles.hostDetail}>{env.detail}</span>
            ) : null}
          </span>
        </div>
      )}

      <div className={styles.hostActions}>
        <Button
          size="small"
          icon={<RefreshCw size={12} />}
          loading={loading}
          onClick={() => void refresh()}
        >
          {t("acp.host.recheck")}
        </Button>
      </div>

      <AcpSectionToggle
        label={t("acp.host.installMethods")}
        open={installOpen}
        onToggle={() => setInstallOpen((current) => !current)}
      >
        {hostScript ? (
          <section className={styles.hostSection}>
            <div className={styles.hostSectionTitle}>
              {t("acp.host.sectionAuto")}
            </div>
            <p className={styles.hostSectionDesc}>
              {env?.can_auto_install
                ? t("acp.host.autoDesc")
                : t("acp.host.autoDescUnavailable")}
            </p>
            <div className={styles.installCommandRow}>
              <pre className={styles.installCommand}>{hostScript}</pre>
              {!ok ? (
                <Button
                  size="small"
                  type="primary"
                  icon={<Download size={12} />}
                  loading={busy}
                  onClick={() => void handleInstall()}
                >
                  {env?.can_auto_install
                    ? t("acp.host.oneClickInstall")
                    : t("acp.host.tryInstall")}
                </Button>
              ) : null}
            </div>
          </section>
        ) : null}

        {scriptPlatforms.length > 0 ? (
          <section className={styles.hostSection}>
            <div className={styles.hostSectionTitle}>
              {t("acp.host.sectionManual")}
            </div>
            <p className={styles.hostSectionDesc}>{t("acp.host.manualDesc")}</p>
            <Segmented
              size="small"
              value={
                scriptPlatforms.includes(platform as (typeof PLATFORMS)[number])
                  ? platform
                  : scriptPlatforms[0]
              }
              onChange={(value) => setPlatform(String(value))}
              options={scriptPlatforms.map((item) => ({
                value: item,
                label: t(`acp.host.platform.${item}`, {
                  current: item === env?.platform ? t("acp.host.thisHost") : "",
                }),
              }))}
            />
            <pre className={styles.hostCode}>{selectedScript}</pre>
            <div className={styles.hostActions}>
              <Button
                size="small"
                icon={<Copy size={12} />}
                disabled={!selectedScript}
                onClick={() =>
                  void copyValue(selectedScript, "acp.host.copiedScript")
                }
              >
                {t("acp.host.copyScript")}
              </Button>
              {env?.docs_url ? (
                <Typography.Link
                  href={env.docs_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("acp.host.docs")}
                </Typography.Link>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className={styles.hostSection}>
          <div className={styles.hostSectionTitle}>
            {t("acp.host.sectionOctop")}
          </div>
          <p className={styles.hostSectionDesc}>{t("acp.host.octopDesc")}</p>
          {env?.agent_prompt ? (
            <pre className={styles.hostPrompt}>{env.agent_prompt}</pre>
          ) : null}
          <div className={styles.hostActions}>
            <Button
              size="small"
              icon={<Copy size={12} />}
              disabled={!env?.agent_prompt}
              onClick={() =>
                void copyValue(env?.agent_prompt ?? "", "acp.host.copiedPrompt")
              }
            >
              {t("acp.host.copyPrompt")}
            </Button>
          </div>
        </section>
      </AcpSectionToggle>
    </div>
  );
}
