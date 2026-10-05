import { useEffect, useRef, useState } from "react";
import { Alert, Button, Spin } from "antd";
import { CheckCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";

import {
  connectorsApi,
  type AgentlyAuthStatus,
} from "../../../api/modules/connectors";
import { apiErrorMessage } from "../../../utils/apiError";
import styles from "./index.module.less";

export function AgentlyAuth({
  instanceId,
  installed,
  onChanged,
}: {
  instanceId: string;
  installed: boolean;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [auth, setAuth] = useState<AgentlyAuthStatus | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [revision, setRevision] = useState(0);
  const mounted = useRef(false);
  const changed = useRef(onChanged);

  useEffect(() => {
    changed.current = onChanged;
  }, [onChanged]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (busy) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      setChecking(true);
      try {
        const result = await connectorsApi.agentlyAuth(instanceId, "status");
        if (!active) return;
        setAuth(result);
        if (result.status === "pending") {
          timer = setTimeout(() => void check(), 2000);
        } else {
          changed.current();
        }
      } catch (err) {
        if (active) setError(err);
      } finally {
        if (active) setChecking(false);
      }
    };
    void check();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [instanceId, busy, revision]);

  const run = async (action: "start" | "logout" | "refresh") => {
    setBusy(true);
    setError(null);
    try {
      const result = await connectorsApi.agentlyAuth(instanceId, action);
      if (mounted.current) setAuth(result);
    } catch (err) {
      if (mounted.current) setError(err);
    } finally {
      if (mounted.current) {
        setBusy(false);
        setRevision((v) => v + 1);
      }
    }
  };

  const statusLabels = {
    idle: t("connectors.agentlyIdle", "尚未授权此邮箱实例"),
    pending: t(
      "connectors.agentlyPending",
      "请打开授权页完成登录，授权结果会自动更新。",
    ),
    authorized: t("connectors.agentlyAuthorized", "邮箱已授权"),
    expired: t("connectors.agentlyExpired", "授权已过期，请重新登录授权"),
    error: t("connectors.agentlyAuthFailed", "邮箱授权失败，请重试"),
  };

  return (
    <div className={`${styles.feishuUserAuthBox} ${styles.agentlyAuthBox}`}>
      <div className={styles.feishuUserAuthTitle}>
        {t("connectors.agentlyAuthTitle", "Agent Mail 邮箱授权")}
      </div>
      <div
        className={
          auth?.status === "authorized"
            ? styles.agentlyAuthSuccess
            : styles.feishuUserAuthHint
        }
        role="status"
      >
        {auth?.status === "authorized" && <CheckCircleOutlined />}
        {auth ? statusLabels[auth.status] : !error && <Spin size="small" />}
      </div>
      {(error || auth?.error) && (
        <Alert
          type="error"
          showIcon
          message={
            error
              ? apiErrorMessage(
                  error,
                  t("connectors.agentlyAuthFailed", "邮箱授权失败，请重试"),
                  t,
                )
              : auth?.error
          }
        />
      )}
      {auth?.status === "pending" && auth.user_code && (
        <p>
          {t("connectors.agentlyUserCode", "授权码")}:{" "}
          <code>{auth.user_code}</code>
        </p>
      )}
      <div className={styles.quickAuthBar}>
        <Button
          type={auth?.status === "authorized" ? "default" : "primary"}
          disabled={!installed || auth?.status === "pending"}
          loading={busy}
          onClick={() => void run("start")}
        >
          {t("connectors.agentlyStart", "登录授权")}
        </Button>
        {auth?.status === "pending" && auth.verification_url && (
          <Button href={auth.verification_url} target="_blank" rel="noreferrer">
            {t("connectors.openAuthorizePage", "打开授权页")}
          </Button>
        )}
        <Button
          disabled={busy}
          loading={checking}
          onClick={() => {
            setError(null);
            setRevision((v) => v + 1);
          }}
        >
          {t("connectors.agentlyCheckStatus", "检查状态")}
        </Button>
        {(auth?.status === "authorized" || auth?.status === "expired") && (
          <Button disabled={busy} onClick={() => void run("refresh")}>
            {t("connectors.agentlyRefresh", "刷新授权")}
          </Button>
        )}
        {auth && auth.status !== "idle" && (
          <Button danger disabled={busy} onClick={() => void run("logout")}>
            {auth.status === "pending"
              ? t("connectors.agentlyCancel", "取消授权")
              : t("connectors.agentlyLogout", "注销授权")}
          </Button>
        )}
      </div>
    </div>
  );
}
