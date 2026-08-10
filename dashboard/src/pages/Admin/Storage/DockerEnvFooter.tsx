/**
 * Docker host environment panel for the Docker backend drawer.
 *
 * Three install paths: auto / manual script / Octop agent prompt.
 */
import { useCallback, useEffect, useState } from "react";
import { Button, Spin, Typography } from "antd";
import { message } from "@/utils/antdMessage";
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Download,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import styles from "./dockerEnvFooter.module.less";

export type DockerEnvStatus =
  | "ready"
  | "installed"
  | "daemon_down"
  | "missing"
  | "skipped"
  | "degraded";

export interface DockerEnvResult {
  status: DockerEnvStatus;
  reason?: string;
  detail?: string;
  platform?: string;
  cli?: boolean;
  daemon?: boolean;
  docs_url?: string;
  install_script?: string;
  agent_prompt?: string;
  can_auto_install?: boolean;
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function DockerEnvFooter() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [env, setEnv] = useState<DockerEnvResult | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await request<DockerEnvResult>(
        "/filesystem/docker-status",
      );
      setEnv(result);
    } catch (err) {
      setEnv({
        status: "degraded",
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleEnsure = async () => {
    setBusy(true);
    try {
      const result = await request<DockerEnvResult>(
        "/filesystem/ensure-docker",
        {
          method: "POST",
        },
      );
      setEnv(result);
      if (result.status === "ready" || result.status === "installed") {
        message.success(t(`storage.dockerEnv.status.${result.status}`));
      } else if (result.status === "skipped") {
        message.info(t("storage.dockerEnv.autoInstallSkipped"));
      } else if (result.status === "daemon_down") {
        message.warning(t("storage.dockerEnv.status.daemon_down"));
      } else {
        message.warning(
          t(`storage.dockerEnv.status.${result.status}`, {
            detail: result.detail ?? "",
          }),
        );
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleCopyScript = async () => {
    const text = env?.install_script ?? "";
    if (!text) return;
    if (await copyText(text)) {
      message.success(t("storage.dockerEnv.copiedScript"));
    } else {
      message.error(t("storage.dockerEnv.copyFailed"));
    }
  };

  const handleCopyPrompt = async () => {
    const text = env?.agent_prompt ?? "";
    if (!text) return;
    if (await copyText(text)) {
      message.success(t("storage.dockerEnv.copiedPrompt"));
    } else {
      message.error(t("storage.dockerEnv.copyFailed"));
    }
  };

  const status = env?.status ?? "missing";
  const ok = status === "ready" || status === "installed";
  const StatusIcon = ok ? CheckCircle2 : AlertCircle;

  return (
    <div className={styles.drawerPanel}>
      <div className={styles.drawerTitle}>
        {t("storage.dockerEnv.drawerTitle")}
      </div>

      {loading && !env ? (
        <div className={styles.statusRow}>
          <Spin size="small" />
          <span className={styles.statusText}>
            {t("storage.dockerEnv.checking")}
          </span>
        </div>
      ) : (
        <div className={styles.statusRow}>
          <StatusIcon
            size={16}
            className={ok ? styles.ok : styles.warn}
            aria-hidden
          />
          <span className={styles.statusText}>
            {t(`storage.dockerEnv.status.${status}`, {
              detail: env?.detail ?? "",
            })}
          </span>
        </div>
      )}

      {/* 1. Auto install */}
      <section className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("storage.dockerEnv.sectionAuto")}
        </div>
        <p className={styles.sectionDesc}>
          {env?.can_auto_install
            ? t("storage.dockerEnv.autoDescReady")
            : t("storage.dockerEnv.autoDescUnavailable")}
        </p>
        <div className={styles.actions}>
          <Button
            size="small"
            icon={<RefreshCw size={12} />}
            loading={loading}
            onClick={() => void refresh()}
          >
            {t("storage.dockerEnv.recheck")}
          </Button>
          {!ok ? (
            <Button
              size="small"
              type="primary"
              icon={<Download size={12} />}
              loading={busy}
              onClick={() => void handleEnsure()}
            >
              {env?.can_auto_install
                ? t("storage.dockerEnv.oneClickInstall")
                : t("storage.dockerEnv.tryInstall")}
            </Button>
          ) : null}
        </div>
      </section>

      {/* 2. Manual install */}
      <section className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("storage.dockerEnv.sectionManual")}
        </div>
        <p className={styles.sectionDesc}>
          {t("storage.dockerEnv.manualDesc")}
        </p>
        {env?.install_script ? (
          <pre className={styles.codeBlock}>{env.install_script}</pre>
        ) : null}
        <div className={styles.actions}>
          <Button
            size="small"
            icon={<Copy size={12} />}
            onClick={() => void handleCopyScript()}
            disabled={!env?.install_script}
          >
            {t("storage.dockerEnv.copyScript")}
          </Button>
          {env?.docs_url ? (
            <Typography.Link
              href={env.docs_url}
              target="_blank"
              rel="noreferrer"
              className={styles.docs}
            >
              {t("storage.dockerEnv.docs")}
            </Typography.Link>
          ) : null}
        </div>
      </section>

      {/* 3. Octop agent install */}
      <section className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("storage.dockerEnv.sectionOctop")}
        </div>
        <p className={styles.sectionDesc}>{t("storage.dockerEnv.octopDesc")}</p>
        {env?.agent_prompt ? (
          <pre className={styles.promptBlock}>{env.agent_prompt}</pre>
        ) : null}
        <div className={styles.actions}>
          <Button
            size="small"
            icon={<Copy size={12} />}
            onClick={() => void handleCopyPrompt()}
            disabled={!env?.agent_prompt}
          >
            {t("storage.dockerEnv.copyPrompt")}
          </Button>
        </div>
      </section>
    </div>
  );
}
