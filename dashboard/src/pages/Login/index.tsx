import {
  useState,
  useEffect,
  useRef,
  useCallback,
  type ReactNode,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Input, Button, Checkbox } from "antd";
import { message } from "@/utils/antdMessage";

import { Fingerprint, KeyRound, Lock, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  clearAuthToken,
  setAuthToken,
  setRememberLoginPreference,
} from "../../api";
import {
  authApi,
  isMfaChallenge,
  type LdapStatus,
  type MfaChallengeResponse,
  type MfaMethod,
  type OauthProviderStatus,
} from "../../api/modules/auth";
import { apiErrorMessage } from "../../utils/apiError";
import { publicUrl } from "../../utils/publicUrl";
import { refreshServerLabels } from "../../i18n";
import { applyUserLocale, applyGuestLocale } from "../../utils/locale";
import { useTheme } from "../../context/ThemeContext";
import {
  isSsoPopup,
  isSsoPopupMessage,
  notifySsoOpener,
  openSsoPopup,
} from "../../utils/ssoPopup";
import {
  isConditionalMediationAvailable,
  isWebAuthnAbortError,
  isWebAuthnAvailable,
  isWebAuthnIpHost,
  webauthnErrorMessage,
  webauthnGet,
  webauthnGetConditional,
} from "../../utils/webauthn";
import feishuIcon from "../../assets/channels/feishu.svg";
import dingtalkIcon from "../../assets/channels/dingtalk.svg";
import wecomIcon from "../../assets/channels/wecom.svg";
import googleIcon from "../../assets/providers/google.svg";
import CaptchaField, { type CaptchaFieldHandle } from "./CaptchaField";
import ForgotPasswordModal from "./ForgotPasswordModal";
import { type PublicCaptchaConfig } from "./captchaAdapters";

type MfaStepMode = "totp" | "recovery" | "passkey";

function providerLabel(
  provider: OauthProviderStatus,
  t: (key: string, opts?: Record<string, string>) => string,
): string {
  const name = provider.display_name.trim();
  if (name) return name;
  return t(`login.providerKind.${provider.kind}`, {
    defaultValue: provider.kind,
  });
}

function providerIcon(provider: OauthProviderStatus): ReactNode {
  if (provider.kind === "feishu") {
    return (
      <img src={feishuIcon} alt="" width={18} height={18} draggable={false} />
    );
  }
  if (provider.kind === "dingtalk") {
    return (
      <img src={dingtalkIcon} alt="" width={18} height={18} draggable={false} />
    );
  }
  if (provider.kind === "wecom") {
    return (
      <img src={wecomIcon} alt="" width={18} height={18} draggable={false} />
    );
  }
  const name = provider.display_name.trim().toLowerCase();
  if (
    provider.kind === "oidc" &&
    (name === "google" || name.includes("google"))
  ) {
    return (
      <img src={googleIcon} alt="" width={18} height={18} draggable={false} />
    );
  }
  return <KeyRound size={18} />;
}

function defaultMfaMode(methods: MfaMethod[]): MfaStepMode {
  // Prefer the factor the user actually enrolled; recovery is a fallback only.
  if (methods.includes("totp")) return "totp";
  if (methods.includes("webauthn")) return "passkey";
  if (methods.includes("recovery")) return "recovery";
  return "totp";
}

function mfaHintKey(methods: MfaMethod[], mode: MfaStepMode): string {
  if (mode === "passkey") return "login.mfaHintPasskey";
  if (mode === "recovery") return "login.mfaHintRecovery";
  if (methods.includes("webauthn") || methods.includes("recovery")) {
    return "login.mfaHint";
  }
  return "login.mfaHintTotp";
}

export default function LoginPage() {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [providers, setProviders] = useState<OauthProviderStatus[]>([]);
  const [ldap, setLdap] = useState<LdapStatus | null>(null);
  const [ssoLoadingKind, setSsoLoadingKind] = useState<string | null>(null);
  const [captchaReady, setCaptchaReady] = useState(false);
  const [captchaResetKey, setCaptchaResetKey] = useState(0);
  const [showForgotHelp, setShowForgotHelp] = useState(false);
  const [captcha, setCaptcha] = useState<PublicCaptchaConfig>({
    provider: "slider",
  });
  const captchaRef = useRef<CaptchaFieldHandle>(null);

  // MFA challenge — mfa_token stays in React state only (never localStorage).
  const [mfaChallenge, setMfaChallenge] = useState<MfaChallengeResponse | null>(
    null,
  );
  const [mfaMode, setMfaMode] = useState<MfaStepMode>("totp");
  const [mfaCode, setMfaCode] = useState("");
  const [passkeyAvailable] = useState(() => isWebAuthnAvailable());
  const [passkeyIpHost] = useState(() => isWebAuthnIpHost());
  const [conditionalOk, setConditionalOk] = useState(false);
  const conditionalAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void applyGuestLocale();
  }, []);

  useEffect(() => {
    let cancelled = false;
    void isConditionalMediationAvailable().then((ok) => {
      if (!cancelled) setConditionalOk(ok);
    });
    return () => {
      cancelled = true;
    };
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
        // Only probe OIDC / captcha after setup is done — otherwise lockdown 503s.
        authApi
          .getOauthStatus()
          .then((next) => {
            if (!cancelled) {
              setProviders(next.providers.filter((item) => item.enabled));
            }
          })
          .catch(() => {});
        authApi
          .getLdapStatus()
          .then((next) => {
            if (!cancelled) setLdap(next);
          })
          .catch(() => {});
        authApi
          .getCaptcha()
          .then((next) => {
            if (!cancelled) setCaptcha(next);
          })
          .catch(() => {
            if (!cancelled) setCaptcha({ provider: "slider" });
          });
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
    if (notifySsoOpener({ ok: false, error: code })) return;
    message.error(
      t(`login.oidcError.${code}`, {
        defaultValue: t("login.oidcError.generic"),
      }),
    );
    navigate("/login", { replace: true });
  }, [navigate, searchParams, t]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!isSsoPopupMessage(event, window.location.origin) || !event.data.ok) {
        if (
          isSsoPopupMessage(event, window.location.origin) &&
          !event.data.ok
        ) {
          setSsoLoadingKind(null);
          const code = event.data.error || "generic";
          message.error(
            t(`login.oidcError.${code}`, {
              defaultValue: t("login.oidcError.generic"),
            }),
          );
        }
        return;
      }
      if (event.data.access_token) {
        setAuthToken(event.data.access_token, event.data.remember ?? true);
      }
      window.location.replace(event.data.redirect || "/chat");
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [t]);

  const resetCaptcha = () => {
    setCaptchaReady(false);
    setCaptchaResetKey((k) => k + 1);
  };

  const finishLogin = useCallback(
    async (accessToken: string, locale: string | null | undefined) => {
      conditionalAbortRef.current?.abort();
      setAuthToken(accessToken, remember);
      setMfaChallenge(null);
      setMfaCode("");
      const applied = await applyUserLocale(locale);
      void refreshServerLabels(applied);
      navigate("/chat", { replace: true });
    },
    [navigate, remember],
  );

  // Conditional UI: passkeys appear in the username autofill when available.
  useEffect(() => {
    if (mfaChallenge || !passkeyAvailable || passkeyIpHost || !conditionalOk) {
      return;
    }
    let cancelled = false;
    const ac = new AbortController();
    conditionalAbortRef.current = ac;
    void (async () => {
      try {
        const options = await authApi.passkeyLoginOptions();
        if (cancelled || ac.signal.aborted) return;
        const credential = await webauthnGetConditional(options, ac.signal);
        if (cancelled || ac.signal.aborted) return;
        setLoading(true);
        const res = await authApi.passkeyLoginVerify(credential);
        await finishLogin(res.access_token, res.user.locale);
      } catch (err) {
        if (cancelled || ac.signal.aborted || isWebAuthnAbortError(err)) {
          return;
        }
        // User dismissed autofill / no matching passkey — stay silent.
        const name =
          err && typeof err === "object" && "name" in err
            ? String((err as { name?: string }).name || "")
            : "";
        if (name === "NotAllowedError") return;
        message.error(
          webauthnErrorMessage(err, t) ??
            apiErrorMessage(err, t("login.passkeyFailed"), t),
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      ac.abort();
      if (conditionalAbortRef.current === ac) {
        conditionalAbortRef.current = null;
      }
    };
  }, [
    conditionalOk,
    finishLogin,
    mfaChallenge,
    passkeyAvailable,
    passkeyIpHost,
    t,
  ]);

  const clearMfaStep = () => {
    setMfaChallenge(null);
    setMfaCode("");
    setPassword("");
    resetCaptcha();
  };

  const onSso = async (kind: string) => {
    setSsoLoadingKind(kind);
    setRememberLoginPreference(remember);
    let popup: Window | null = null;
    if (kind !== "oidc") {
      popup = openSsoPopup();
    }
    try {
      const { authorization_url } = await authApi.startOauth(kind, "/chat");
      if (kind === "oidc") {
        window.location.href = authorization_url;
        return;
      }
      if (popup && !popup.closed) {
        popup.location.href = authorization_url;
        const timer = window.setInterval(() => {
          if (!popup || popup.closed) {
            window.clearInterval(timer);
            setSsoLoadingKind((current) => (current === kind ? null : current));
          }
        }, 400);
      } else {
        popup?.close();
        message.error(t("account.ssoPopupBlocked"));
        setSsoLoadingKind(null);
      }
    } catch (err) {
      popup?.close();
      message.error(apiErrorMessage(err, t("login.oidcStartFailed"), t));
      setSsoLoadingKind(null);
    }
  };

  const handleLogin = async () => {
    if (!username || !password || !captchaReady) return;
    setLoading(true);
    try {
      const token = await captchaRef.current?.getToken();
      const res = await authApi.login(username, password, token);
      if (isMfaChallenge(res)) {
        setMfaChallenge(res);
        setMfaMode(defaultMfaMode(res.methods));
        setMfaCode("");
        setPassword("");
        return;
      }
      await finishLogin(res.access_token, res.user.locale);
    } catch (err) {
      message.error(apiErrorMessage(err, t("login.failed"), t));
      resetCaptcha();
    } finally {
      setLoading(false);
    }
  };

  const handleMfaVerify = async () => {
    if (!mfaChallenge || !mfaCode.trim()) return;
    setLoading(true);
    try {
      const method: MfaMethod = mfaMode === "recovery" ? "recovery" : "totp";
      const res = await authApi.mfaVerify({
        mfa_token: mfaChallenge.mfa_token,
        method,
        code: mfaCode.trim(),
      });
      await finishLogin(res.access_token, res.user.locale);
    } catch (err) {
      message.error(apiErrorMessage(err, t("login.mfaFailed"), t));
    } finally {
      setLoading(false);
    }
  };

  const handleMfaPasskey = async () => {
    if (!mfaChallenge) return;
    if (!passkeyAvailable) {
      message.warning(t("login.mfaPasskeyUnavailable"));
      return;
    }
    if (passkeyIpHost) {
      message.warning(t("apiErrors.WEBAUTHN_INVALID_DOMAIN"));
      return;
    }
    setLoading(true);
    try {
      const options = await authApi.mfaPasskeyOptions(mfaChallenge.mfa_token);
      const credential = await webauthnGet(options);
      const res = await authApi.mfaVerify({
        mfa_token: mfaChallenge.mfa_token,
        method: "webauthn",
        credential,
      });
      await finishLogin(res.access_token, res.user.locale);
    } catch (err) {
      message.error(
        webauthnErrorMessage(err, t) ??
          apiErrorMessage(err, t("login.mfaFailed"), t),
      );
    } finally {
      setLoading(false);
    }
  };

  const handlePasskeyLogin = async () => {
    if (!passkeyAvailable) {
      message.warning(t("login.passkeyHttpsRequired"));
      return;
    }
    if (passkeyIpHost) {
      message.warning(t("apiErrors.WEBAUTHN_INVALID_DOMAIN"));
      return;
    }
    // Modal ceremony — abort Conditional UI so only one get() runs.
    conditionalAbortRef.current?.abort();
    setLoading(true);
    try {
      const options = await authApi.passkeyLoginOptions();
      const credential = await webauthnGet(options);
      const res = await authApi.passkeyLoginVerify(credential);
      await finishLogin(res.access_token, res.user.locale);
    } catch (err) {
      if (isWebAuthnAbortError(err)) return;
      message.error(
        webauthnErrorMessage(err, t) ??
          apiErrorMessage(err, t("login.passkeyFailed"), t),
      );
    } finally {
      setLoading(false);
    }
  };

  if (isSsoPopup() && searchParams.get("oidc_error")) {
    return null;
  }

  const cardStyle = {
    width: "100%",
    maxWidth: 360,
    padding: "48px 32px 40px",
    background: "var(--fn-bg-elevated)",
    borderRadius: 16,
    boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
    border: "1px solid var(--fn-border-primary)",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 20,
    margin: "0 16px",
  };

  const logo = (
    <img
      src={
        isDark
          ? publicUrl("logo_horizontal_white.png")
          : publicUrl("logo_horizontal_dark.png")
      }
      alt="Octop"
      style={{
        height: 48,
        width: "auto",
        maxWidth: 260,
        objectFit: "contain",
        display: "block",
      }}
    />
  );

  if (mfaChallenge) {
    const methods = mfaChallenge.methods;
    const showTotp = methods.includes("totp");
    const showRecovery = methods.includes("recovery");
    const showPasskey = methods.includes("webauthn");
    const showCodeField =
      (mfaMode === "totp" && showTotp) ||
      (mfaMode === "recovery" && showRecovery);
    const codeLabel =
      mfaMode === "recovery" ? t("login.mfaRecovery") : t("login.mfaTotp");
    const codePlaceholder =
      mfaMode === "recovery"
        ? t("login.mfaRecoveryPlaceholder")
        : t("login.mfaTotpPlaceholder");

    return (
      <div
        style={{
          minHeight: "100dvh",
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding:
            "max(24px, env(safe-area-inset-top, 0px)) max(16px, env(safe-area-inset-right, 0px)) max(24px, env(safe-area-inset-bottom, 0px)) max(16px, env(safe-area-inset-left, 0px))",
          background: "var(--fn-bg-layout)",
          transition: "background var(--fn-transition)",
        }}
      >
        <div style={cardStyle}>
          {logo}
          <h2
            style={{
              fontSize: 20,
              fontWeight: 600,
              color: "var(--fn-text-primary)",
              margin: 0,
              textAlign: "center",
            }}
          >
            {t("login.mfaTitle")}
          </h2>
          {mfaChallenge.user_hint ? (
            <p
              style={{
                margin: 0,
                fontSize: 13,
                color: "var(--fn-text-tertiary)",
                textAlign: "center",
              }}
            >
              {mfaChallenge.user_hint}
            </p>
          ) : null}
          <p
            style={{
              margin: 0,
              fontSize: 13,
              lineHeight: 1.5,
              color: "var(--fn-text-tertiary)",
              textAlign: "center",
            }}
          >
            {t(mfaHintKey(methods, mfaMode))}
          </p>

          {showCodeField ? (
            <>
              <Input
                prefix={
                  <Lock
                    size={16}
                    style={{ color: "var(--fn-text-quaternary)" }}
                  />
                }
                placeholder={codePlaceholder}
                aria-label={codeLabel}
                size="large"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                onPressEnter={() => void handleMfaVerify()}
                autoFocus
                autoComplete="one-time-code"
                style={{ borderRadius: 10 }}
              />
              <Button
                type="primary"
                size="large"
                block
                loading={loading}
                onClick={() => void handleMfaVerify()}
                disabled={!mfaCode.trim()}
                style={{ borderRadius: 10, height: 44, fontWeight: 500 }}
              >
                {t("login.mfaVerify")}
              </Button>
            </>
          ) : null}

          {mfaMode === "passkey" && showPasskey ? (
            <Button
              type="primary"
              size="large"
              block
              icon={<Fingerprint size={18} />}
              loading={loading}
              onClick={() => void handleMfaPasskey()}
              style={{ borderRadius: 10, height: 44, fontWeight: 500 }}
            >
              {t("login.mfaUsePasskey")}
            </Button>
          ) : null}

          <div
            style={{
              width: "100%",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {showTotp && mfaMode !== "totp" ? (
              <Button type="link" onClick={() => setMfaMode("totp")}>
                {t("login.mfaUseTotp")}
              </Button>
            ) : null}
            {showRecovery && mfaMode !== "recovery" ? (
              <Button type="link" onClick={() => setMfaMode("recovery")}>
                {t("login.mfaUseRecovery")}
              </Button>
            ) : null}
            {showPasskey && mfaMode !== "passkey" ? (
              <Button
                type="link"
                icon={<Fingerprint size={16} />}
                onClick={() => setMfaMode("passkey")}
              >
                {t("login.mfaUsePasskey")}
              </Button>
            ) : null}
            {showPasskey && !passkeyAvailable ? (
              <p
                style={{
                  margin: 0,
                  fontSize: 12,
                  lineHeight: 1.5,
                  color: "var(--fn-text-tertiary)",
                  textAlign: "center",
                }}
              >
                {t("login.mfaPasskeyUnavailable")}
              </p>
            ) : null}
            <Button type="link" onClick={clearMfaStep}>
              {t("login.mfaBack")}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: "100dvh",
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding:
          "max(24px, env(safe-area-inset-top, 0px)) max(16px, env(safe-area-inset-right, 0px)) max(24px, env(safe-area-inset-bottom, 0px)) max(16px, env(safe-area-inset-left, 0px))",
        background: "var(--fn-bg-layout)",
        transition: "background var(--fn-transition)",
      }}
    >
      <div style={cardStyle}>
        {logo}

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
          autoComplete="username webauthn"
          name="username"
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
          autoComplete="current-password"
          name="password"
          style={{ borderRadius: 10 }}
        />

        {ldap?.enabled && (
          <p
            style={{
              margin: 0,
              marginTop: -8,
              width: "100%",
              fontSize: 12,
              lineHeight: 1.5,
              color: "var(--fn-text-tertiary)",
              textAlign: "center",
            }}
          >
            {t("login.ldapHint", {
              name: ldap.display_name.trim() || t("adminSso.ldap.kind"),
            })}
          </p>
        )}

        <CaptchaField
          ref={captchaRef}
          config={captcha}
          resetKey={captchaResetKey}
          slideHint={t("login.slideHint")}
          slideVerifiedLabel={t("login.slideVerified")}
          unsupportedLabel={t("login.unsupportedCaptcha")}
          onReadyChange={setCaptchaReady}
        />

        <Button
          type="primary"
          size="large"
          block
          loading={loading}
          onClick={handleLogin}
          disabled={!username || !password || !captchaReady}
          style={{ borderRadius: 10, height: 44, fontWeight: 500 }}
        >
          {t("login.submit")}
        </Button>

        {passkeyAvailable && !passkeyIpHost ? (
          conditionalOk ? (
            <Button
              type="link"
              block
              icon={<Fingerprint size={16} />}
              loading={loading}
              onClick={() => void handlePasskeyLogin()}
              style={{ height: 36, fontWeight: 500 }}
            >
              {t("login.passkeySignIn")}
            </Button>
          ) : (
            <Button
              size="large"
              block
              icon={<Fingerprint size={18} />}
              loading={loading}
              onClick={() => void handlePasskeyLogin()}
              style={{ borderRadius: 10, height: 44, fontWeight: 500 }}
            >
              {t("login.passkeySignIn")}
            </Button>
          )
        ) : (
          <p
            style={{
              margin: 0,
              marginTop: -8,
              width: "100%",
              fontSize: 12,
              lineHeight: 1.5,
              color: "var(--fn-text-tertiary)",
              textAlign: "center",
            }}
          >
            {passkeyIpHost
              ? t("apiErrors.WEBAUTHN_INVALID_DOMAIN")
              : t("login.passkeyHttpsRequired")}
          </p>
        )}

        <div
          style={{
            width: "100%",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              width: "100%",
            }}
          >
            <Checkbox
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              style={{
                margin: 0,
                fontSize: 13,
                color: "var(--fn-text-tertiary)",
              }}
            >
              {t("login.remember")}
            </Checkbox>
            <button
              type="button"
              data-testid="login-forgot-password-toggle"
              onClick={() => setShowForgotHelp(true)}
              style={{
                margin: 0,
                padding: 0,
                border: "none",
                background: "none",
                cursor: "pointer",
                fontSize: 13,
                lineHeight: 1.5,
                color: "var(--fn-text-tertiary)",
                flexShrink: 0,
              }}
            >
              {t("login.forgotPassword", "Forgot password?")}
            </button>
          </div>
          <ForgotPasswordModal
            open={showForgotHelp}
            onClose={() => setShowForgotHelp(false)}
          />
        </div>

        {providers.length > 0 && (
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
            {providers.map((provider) => (
              <Button
                key={provider.kind}
                size="large"
                block
                icon={providerIcon(provider)}
                loading={ssoLoadingKind === provider.kind}
                onClick={() => void onSso(provider.kind)}
                style={{ borderRadius: 10, height: 44, fontWeight: 500 }}
              >
                {t("login.oidcWith", { name: providerLabel(provider, t) })}
              </Button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
