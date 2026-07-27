import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Space, Spin, Typography, message } from "antd";
import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { pollCodexOAuth, startCodexOAuth } from "../providerApi";

interface CodexOAuthConnectProps {
  onSuccess: () => void | Promise<void>;
}

const POLL_INTERVAL_MS = 3000;

export function CodexOAuthConnect({ onSuccess }: CodexOAuthConnectProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [device, setDevice] = useState<{
    stateId: string;
    userCode: string;
    verificationUrl: string;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const handleLogin = useCallback(async () => {
    setLoading(true);
    try {
      const { state_id, user_code, verification_url } = await startCodexOAuth();
      setDevice({
        stateId: state_id,
        userCode: user_code,
        verificationUrl: verification_url,
      });
      window.open(verification_url, "_blank", "noopener,noreferrer");

      pollRef.current = setInterval(async () => {
        try {
          const pending = await pollCodexOAuth(state_id);
          if (pending.status === "ok") {
            stopPolling();
            setDevice(null);
            setLoading(false);
            message.success(t("models.codexOAuthSuccess"));
            await onSuccess();
          } else if (pending.status === "error") {
            stopPolling();
            setDevice(null);
            setLoading(false);
            message.error(
              t("models.codexOAuthFailed", {
                error: pending.error ?? "unknown",
              }),
            );
          }
        } catch {
          stopPolling();
          setDevice(null);
          setLoading(false);
          message.error(t("models.codexOAuthFailed", { error: "poll" }));
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("models.codexOAuthStartFailed"),
      );
      setLoading(false);
    }
  }, [onSuccess, stopPolling, t]);

  const handleCancel = useCallback(() => {
    stopPolling();
    setDevice(null);
    setLoading(false);
  }, [stopPolling]);

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Alert
        type="warning"
        showIcon
        message={t("models.codexOAuthDisclaimer")}
      />
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        {t("models.codexOAuthHint")}
      </Typography.Paragraph>

      {device ? (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            {t("models.codexOAuthDeviceHint")}
          </Typography.Paragraph>
          <Typography.Text
            copyable={{ text: device.userCode }}
            style={{ fontSize: 28, fontWeight: 600, letterSpacing: 4 }}
          >
            {device.userCode}
          </Typography.Text>
          <Space>
            <Button
              icon={<ExternalLink size={14} />}
              onClick={() =>
                window.open(
                  device.verificationUrl,
                  "_blank",
                  "noopener,noreferrer",
                )
              }
            >
              {t("models.codexOAuthOpenVerification")}
            </Button>
            <Button onClick={handleCancel}>{t("common.cancel")}</Button>
          </Space>
          <Space>
            <Spin size="small" />
            <Typography.Text type="secondary">
              {t("models.codexOAuthWaiting")}
            </Typography.Text>
          </Space>
        </Space>
      ) : (
        <Button
          type="primary"
          loading={loading}
          onClick={() => void handleLogin()}
        >
          {t("models.codexOAuthLogin")}
        </Button>
      )}
    </Space>
  );
}
