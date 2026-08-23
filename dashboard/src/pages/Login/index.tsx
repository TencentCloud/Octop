import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Input, Button } from "antd";
import { message } from "@/utils/antdMessage";

import { Lock, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clearAuthToken, setAuthToken } from "../../api";
import { authApi, type OidcStatus } from "../../api/modules/auth";
import { apiErrorMessage } from "../../utils/apiError";
import { refreshServerLabels } from "../../i18n";
import { applyUserLocale, applyGuestLocale } from "../../utils/locale";
import { useTheme } from "../../context/ThemeContext";
import SlideCaptcha from "./SlideCaptcha";

export default function LoginPage() {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [oidc, setOidc] = useState<OidcStatus | null>(null);
  const [oidcLoading, setOidcLoading] = useState(false);
  const [slideVerified, setSlideVerified] = useState(false);
  const [slideResetKey, setSlideResetKey] = useState(0);

  // If no admin exists, redirect to /setup so the wizard can bootstrap one.
  useEffect(() => {
    void applyGuestLocale();
  }, []);

  useEffect(() => {
    let cancelled = false;
    authApi
      .getAuthStatus()
      .then((status) => {
        if (cancelled) return;
        if (status.setup_required) {
          clearAuthToken();
          navigate("/setup", { replace: true });
          return;
        }
        // Only probe OIDC after setup is done — otherwise lockdown 503s.
        authApi
          .getOidcStatus()
          .then((next) => {
            if (!cancelled) setOidc(next);
          })
          .catch(() => {});
      })
      .catch(() => {
        // Backend unreachable — let the user attempt login and show a real
        // error from the request itself; redirecting blindly to /setup
        // would mask the actual problem.
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  useEffect(() => {
    const code = searchParams.get("oidc_error");
    if (!code) return;
    message.error(
      t(`login.oidcError.${code}`, {
        defaultValue: t("login.oidcError.generic"),
      }),
    );
    navigate("/login", { replace: true });
  }, [navigate, searchParams, t]);

  const resetSlide = () => {
    setSlideVerified(false);
    setSlideResetKey((k) => k + 1);
  };

  const onOidc = async () => {
    setOidcLoading(true);
    try {
      const { authorization_url } = await authApi.startOidc("/chat");
      window.location.href = authorization_url;
    } catch (err) {
      message.error(apiErrorMessage(err, t("login.oidcStartFailed"), t));
      setOidcLoading(false);
    }
  };

  const handleLogin = async () => {
    if (!username || !password || !slideVerified) return;
    setLoading(true);
    try {
      const res = await authApi.login(username, password);
      setAuthToken(res.access_token);
      await applyUserLocale(res.user.locale);
      void refreshServerLabels(res.user.locale);
      navigate("/chat", { replace: true });
    } catch (err) {
      message.error(apiErrorMessage(err, t("login.failed"), t));
      resetSlide();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--fn-bg-layout)",
        transition: "background var(--fn-transition)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 360,
          padding: "48px 32px 40px",
          background: "var(--fn-bg-elevated)",
          borderRadius: 16,
          boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
          border: "1px solid var(--fn-border-primary)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 20,
          margin: "0 16px",
        }}
      >
        <img
          src={isDark ? "/logo_name_dark.png" : "/logo_name.png"}
          alt="Octop"
          style={{
            height: 48,
            width: "auto",
            maxWidth: 260,
            objectFit: "contain",
            display: "block",
          }}
        />

        <h2
          style={{
            fontSize: 20,
            fontWeight: 600,
            color: "var(--fn-text-primary)",
            margin: 0,
            textAlign: "center",
          }}
        >
          {t("login.title")}
        </h2>

        <Input
          prefix={
            <User size={16} style={{ color: "var(--fn-text-quaternary)" }} />
          }
          placeholder={t("login.username")}
          size="large"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          style={{ borderRadius: 10 }}
        />

        <Input.Password
          prefix={
            <Lock size={16} style={{ color: "var(--fn-text-quaternary)" }} />
          }
          placeholder={t("login.password")}
          size="large"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onPressEnter={handleLogin}
          style={{ borderRadius: 10 }}
        />

        <SlideCaptcha
          hint={t("login.slideHint")}
          verifiedLabel={t("login.slideVerified")}
          onVerified={() => setSlideVerified(true)}
          resetKey={slideResetKey}
        />

        <Button
          type="primary"
          size="large"
          block
          loading={loading}
          onClick={handleLogin}
          disabled={!username || !password || !slideVerified}
          style={{ borderRadius: 10, height: 44, fontWeight: 500 }}
        >
          {t("login.submit")}
        </Button>

        {oidc?.enabled && (
          <>
            <div
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 12,
                color: "var(--fn-text-tertiary)",
                fontSize: 13,
              }}
            >
              <span
                style={{
                  flex: 1,
                  height: 1,
                  background: "var(--fn-border-primary)",
                }}
              />
              {t("login.or")}
              <span
                style={{
                  flex: 1,
                  height: 1,
                  background: "var(--fn-border-primary)",
                }}
              />
            </div>
            <Button
              size="large"
              block
              loading={oidcLoading}
              onClick={onOidc}
              style={{ borderRadius: 10, height: 44, fontWeight: 500 }}
            >
              {t("login.oidcWith", { name: oidc.display_name })}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
