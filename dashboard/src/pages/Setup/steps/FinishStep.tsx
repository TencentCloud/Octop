import { useEffect, useState } from "react";
import { Spin, Alert, Button, Typography, Space } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { authApi, isMfaChallenge } from "../../../api/modules/auth";
import { setAuthToken } from "../../../api/request";
import { refreshServerLabels } from "../../../i18n";
import { applyUserLocale } from "../../../utils/locale";
import {
  wizardApi,
  wizardSession,
  resolveSetupProbeToken,
} from "../wizardClient";
import type { ProviderDraft } from "../wizardClient";

const { Text } = Typography;

interface Props {
  adminCreds: { username: string; password: string };
  providerDraft: ProviderDraft | null;
}

export default function FinishStep({ adminCreds, providerDraft }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [running, setRunning] = useState(true);
  const [errors, setErrors] = useState<{ login?: string; provider?: string }>(
    {},
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const wizardToken = await resolveSetupProbeToken();

      if (wizardToken) {
        try {
          await wizardApi.finish(
            { provider_draft: providerDraft },
            wizardToken,
          );
        } catch (e) {
          if (!cancelled) {
            setErrors((s) => ({
              ...s,
              provider: e instanceof Error ? e.message : String(e),
            }));
          }
        }
      } else if (!wizardToken && !cancelled) {
        setErrors((s) => ({
          ...s,
          provider: t("wizard.sessionExpired"),
        }));
      }

      try {
        const r = await authApi.login(adminCreds.username, adminCreds.password);
        if (isMfaChallenge(r)) {
          throw new Error(t("login.mfaTitle"));
        }
        setAuthToken(r.access_token);
        await applyUserLocale(r.user.locale);
        void refreshServerLabels(r.user.locale);
      } catch (e) {
        if (!cancelled) {
          setErrors((s) => ({
            ...s,
            login: e instanceof Error ? e.message : String(e),
          }));
          setRunning(false);
        }
        return;
      }

      wizardSession.clearAll();
      if (!cancelled) {
        setRunning(false);
        setTimeout(() => {
          if (!cancelled) navigate("/chat", { replace: true });
        }, 400);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [adminCreds, providerDraft, navigate, t]);

  if (running && !errors.login) {
    return (
      <Space direction="vertical" align="center" style={{ width: "100%" }}>
        <Spin />
        <Text type="secondary">{t("wizard.finish.running")}</Text>
      </Space>
    );
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      {errors.login && (
        <Alert type="error" showIcon message={t("wizard.finish.loginFailed")} />
      )}
      {errors.provider && !errors.login && (
        <Alert
          type="warning"
          showIcon
          message={t("wizard.finish.providerFailed")}
        />
      )}
      <Button
        type="primary"
        block
        onClick={() => {
          wizardSession.clearAll();
          navigate("/login", { replace: true });
        }}
      >
        {t("wizard.finish.fallbackToLogin")}
      </Button>
    </Space>
  );
}
