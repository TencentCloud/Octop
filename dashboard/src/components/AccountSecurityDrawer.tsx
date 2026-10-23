import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Space,
  Spin,
  Tag,
} from "antd";
import { Fingerprint, KeyRound, ShieldCheck } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  authApi,
  type MfaPasskeyInfo,
  type MfaStatus,
  type OctopUser,
} from "../api/modules/auth";
import { apiErrorMessage, isNotFoundApiError } from "../utils/apiError";
import {
  formatServerDateTime,
  formatServerIsoDateTime,
} from "../utils/formatMessageTime";
import { useServerTimezone } from "../hooks/useServerTimezone";
import { useIsMobile } from "../hooks/useIsMobile";
import {
  isWebAuthnAvailable,
  isWebAuthnIpHost,
  webauthnCreate,
  webauthnErrorMessage,
} from "../utils/webauthn";
import styles from "./AccountSecurityDrawer.module.less";

type ReauthAction =
  | { kind: "totp_begin" }
  | { kind: "totp_disable" }
  | { kind: "passkey_add"; name: string }
  | { kind: "passkey_remove"; credentialId: string }
  | { kind: "recovery_regen" };

interface AccountSecurityDrawerProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Account MFA / passkey management. Uses SPEC routes under ``/api/auth/mfa/*``.
 * If routes are missing (404), show a clear unavailable message.
 */
export default function AccountSecurityDrawer({
  open,
  onClose,
}: AccountSecurityDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const timeZone = useServerTimezone();
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [profile, setProfile] = useState<OctopUser | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState(false);

  const [reauthOpen, setReauthOpen] = useState(false);
  const [reauthAction, setReauthAction] = useState<ReauthAction | null>(null);
  const [reauthForm] = Form.useForm<{ password: string; passkeyName?: string }>();

  const [totpUri, setTotpUri] = useState<string | null>(null);
  const [totpReauth, setTotpReauth] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState("");

  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const passkeyIpHost = isWebAuthnIpHost();
  const passkeyOk = isWebAuthnAvailable() && !passkeyIpHost;

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setUnavailable(false);
    try {
      const [next, me] = await Promise.all([
        authApi.mfaStatus(),
        authApi.me().catch(() => null),
      ]);
      setStatus(next);
      if (me) setProfile(me);
    } catch (err) {
      if (isNotFoundApiError(err)) {
        setUnavailable(true);
        setStatus(null);
      } else {
        message.error(apiErrorMessage(err, t("account.securityLoadFailed"), t));
      }
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!open) return;
    void loadStatus();
    setTotpUri(null);
    setTotpReauth(null);
    setTotpCode("");
    setRecoveryCodes(null);
  }, [open, loadStatus]);

  const requestReauth = (action: ReauthAction) => {
    setReauthAction(action);
    reauthForm.resetFields();
    setReauthOpen(true);
  };

  /** Removing the last factor turns off MFA — confirm before password reauth. */
  const requestRemoveFactor = (action: ReauthAction) => {
    if (!status?.is_last_factor) {
      requestReauth(action);
      return;
    }
    Modal.confirm({
      title: t("account.securityDisableMfaTitle"),
      content: t("account.securityDisableMfaHint"),
      okText: t("common.confirm"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: () => {
        requestReauth(action);
      },
    });
  };

  const runWithReauth = async (password: string, action: ReauthAction) => {
    setBusy(true);
    try {
      const { reauth_token } = await authApi.mfaReauth(password);
      setReauthOpen(false);

      switch (action.kind) {
        case "totp_begin": {
          const begin = await authApi.mfaTotpBegin(reauth_token);
          setTotpUri(begin.otpauth_uri);
          setTotpReauth(reauth_token);
          setTotpCode("");
          break;
        }
        case "totp_disable": {
          await authApi.mfaTotpDisable(reauth_token);
          message.success(t("account.securityDisableSuccess"));
          setTotpUri(null);
          setTotpReauth(null);
          await loadStatus();
          break;
        }
        case "passkey_add": {
          const options = await authApi.mfaPasskeyRegisterOptions(reauth_token);
          const credential = await webauthnCreate(options);
          const label = action.name.trim();
          await authApi.mfaPasskeyRegisterVerify(
            reauth_token,
            credential,
            label || undefined,
          );
          message.success(t("account.securityPasskeyAdded"));
          await loadStatus();
          break;
        }
        case "passkey_remove": {
          await authApi.mfaPasskeyRemove(reauth_token, action.credentialId);
          message.success(t("account.securityPasskeyRemoved"));
          await loadStatus();
          break;
        }
        case "recovery_regen": {
          const result = await authApi.mfaRecoveryRegenerate(reauth_token);
          setRecoveryCodes(result.recovery_codes ?? []);
          message.success(t("account.securityRecoveryRegenSuccess"));
          await loadStatus();
          break;
        }
      }
    } catch (err) {
      message.error(
        webauthnErrorMessage(err, t) ??
          apiErrorMessage(err, t("account.securityReauthFailed"), t),
      );
    } finally {
      setBusy(false);
    }
  };

  const confirmTotp = async () => {
    if (!totpReauth || !totpCode.trim()) return;
    setBusy(true);
    try {
      const result = await authApi.mfaTotpConfirm(totpReauth, totpCode.trim());
      setTotpUri(null);
      setTotpReauth(null);
      setTotpCode("");
      if (result.recovery_codes?.length) {
        setRecoveryCodes(result.recovery_codes);
      }
      message.success(t("account.securityEnrollSuccess"));
      await loadStatus();
    } catch (err) {
      message.error(apiErrorMessage(err, t("login.mfaFailed"), t));
    } finally {
      setBusy(false);
    }
  };

  const formatPasskeyTime = (raw: MfaPasskeyInfo["last_used_at"]) => {
    if (raw == null || raw === "") {
      return t("account.securityPasskeyNeverUsed");
    }
    let formatted = "";
    if (typeof raw === "string" && Number.isNaN(Number(raw))) {
      formatted = formatServerIsoDateTime(raw, timeZone);
    } else {
      const n = typeof raw === "number" ? raw : Number(raw);
      if (Number.isFinite(n) && n > 0) {
        const epochSec = n > 1e12 ? Math.floor(n / 1000) : n;
        formatted = formatServerDateTime(epochSec, timeZone);
      }
    }
    if (!formatted || formatted === "—") {
      return t("account.securityPasskeyNeverUsed");
    }
    return t("account.securityPasskeyLastUsed", { time: formatted });
  };

  const hasPassword = profile?.has_password !== false;
  const ssoLinked = Boolean(
    profile?.sso_linked || (profile?.sso_identities?.length ?? 0) > 0,
  );
  const ssoOnly = profile != null && !hasPassword && ssoLinked;
  const canEnroll = !unavailable && !ssoOnly;
  const hasFactor =
    Boolean(status?.totp_verified) || (status?.passkeys.length ?? 0) > 0;
  const passkeyCount = status?.passkeys?.length ?? 0;

  const body = (
    <div className={styles.body}>
      {loading ? (
        <div className={styles.loading}>
          <Spin />
        </div>
      ) : unavailable ? (
        <Alert
          type="info"
          showIcon
          message={t("account.securityUnavailable")}
        />
      ) : (
        <>
          <div className={styles.introBlock}>
            <p className={styles.intro}>{t("account.securityHint")}</p>
            <p className={styles.note}>{t("account.securityCliNote")}</p>
          </div>
          {(ssoLinked || ssoOnly) && (
            <Alert
              type="warning"
              showIcon
              message={
                ssoOnly
                  ? t("account.securitySsoOnly")
                  : t("account.securitySsoBypass")
              }
            />
          )}

          <div className={styles.stack}>
            <section className={styles.card}>
              <div className={styles.cardRow}>
                <div className={styles.cardMain}>
                  <span
                    className={`${styles.iconWrap} ${
                      status?.totp_verified ? styles.iconWrapOn : ""
                    }`}
                    aria-hidden
                  >
                    <ShieldCheck size={18} strokeWidth={1.9} />
                  </span>
                  <div className={styles.cardMeta}>
                    <div className={styles.cardTitleRow}>
                      <h3 className={styles.cardTitle}>
                        {t("account.securityTotp")}
                      </h3>
                      <Tag
                        className={styles.statusTag}
                        color={status?.totp_verified ? "success" : "default"}
                      >
                        {status?.totp_verified
                          ? t("account.securityTotpEnabled")
                          : t("account.securityTotpDisabled")}
                      </Tag>
                    </div>
                    <p className={styles.cardDesc}>
                      {t("account.securityTotpDesc")}
                    </p>
                  </div>
                </div>
                <div className={styles.cardSide}>
                  {!totpUri && canEnroll ? (
                    !status?.totp_verified ? (
                      <Button
                        type="primary"
                        disabled={busy}
                        onClick={() => requestReauth({ kind: "totp_begin" })}
                      >
                        {t("account.securityTotpEnroll")}
                      </Button>
                    ) : (
                      <Button
                        danger
                        disabled={busy}
                        onClick={() =>
                          requestRemoveFactor({ kind: "totp_disable" })
                        }
                      >
                        {t("account.securityTotpDisable")}
                      </Button>
                    )
                  ) : null}
                </div>
              </div>

              {totpUri ? (
                <div className={styles.enrollBox}>
                  <p className={styles.cardDesc}>
                    {t("account.securityTotpScan")}
                  </p>
                  <div className={styles.qrWrap}>
                    <QRCodeSVG value={totpUri} size={168} />
                  </div>
                  <Input
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value)}
                    placeholder={t("account.securityTotpCode")}
                    maxLength={8}
                    autoComplete="one-time-code"
                    size="large"
                  />
                  <Space wrap>
                    <Button
                      type="primary"
                      loading={busy}
                      disabled={!totpCode.trim()}
                      onClick={() => void confirmTotp()}
                    >
                      {t("account.securityTotpConfirm")}
                    </Button>
                    <Button
                      onClick={() => {
                        setTotpUri(null);
                        setTotpReauth(null);
                        setTotpCode("");
                      }}
                    >
                      {t("common.cancel")}
                    </Button>
                  </Space>
                </div>
              ) : null}
            </section>

            <section className={styles.card}>
              <div className={styles.cardRow}>
                <div className={styles.cardMain}>
                  <span
                    className={`${styles.iconWrap} ${
                      passkeyCount > 0 ? styles.iconWrapOn : ""
                    }`}
                    aria-hidden
                  >
                    <Fingerprint size={18} strokeWidth={1.9} />
                  </span>
                  <div className={styles.cardMeta}>
                    <div className={styles.cardTitleRow}>
                      <h3 className={styles.cardTitle}>
                        {t("account.securityPasskeys")}
                      </h3>
                      {passkeyCount > 0 ? (
                        <Tag className={styles.statusTag} color="success">
                          {t("account.securityPasskeyCount", {
                            count: passkeyCount,
                          })}
                        </Tag>
                      ) : null}
                    </div>
                  </div>
                </div>
                <div className={styles.cardSide}>
                  {canEnroll && passkeyOk ? (
                    <Button
                      type="primary"
                      disabled={busy}
                      onClick={() =>
                        requestReauth({ kind: "passkey_add", name: "" })
                      }
                    >
                      {t("account.securityPasskeyAdd")}
                    </Button>
                  ) : null}
                </div>
              </div>
              <p className={styles.cardDescFull}>
                {passkeyCount === 0
                  ? t("account.securityPasskeyEmpty")
                  : t("account.securityPasskeyDesc")}
              </p>

              {!passkeyOk ? (
                <Alert
                  type="info"
                  showIcon
                  message={
                    passkeyIpHost
                      ? t("account.securityPasskeyIpHost", {
                          host: window.location.hostname,
                          port: window.location.port || "80",
                        })
                      : t("account.securityPasskeyHttps")
                  }
                />
              ) : null}

              {passkeyCount > 0 ? (
                <ul className={styles.passkeyList}>
                  {(status?.passkeys ?? []).map((item) => (
                    <li key={item.credential_id} className={styles.passkeyRow}>
                      <div className={styles.passkeyMeta}>
                        <span className={styles.passkeyName}>
                          {item.name.trim() ||
                            t("account.securityPasskeyDefaultName")}
                        </span>
                        <span className={styles.passkeySub}>
                          {formatPasskeyTime(item.last_used_at)}
                        </span>
                      </div>
                      {canEnroll ? (
                        <Button
                          type="link"
                          danger
                          size="small"
                          disabled={busy}
                          onClick={() =>
                            requestRemoveFactor({
                              kind: "passkey_remove",
                              credentialId: item.credential_id,
                            })
                          }
                        >
                          {t("account.securityPasskeyRemove")}
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>

            <section className={styles.card}>
              <div className={styles.cardRow}>
                <div className={styles.cardMain}>
                  <span
                    className={`${styles.iconWrap} ${
                      hasFactor ? styles.iconWrapOn : ""
                    }`}
                    aria-hidden
                  >
                    <KeyRound size={18} strokeWidth={1.9} />
                  </span>
                  <div className={styles.cardMeta}>
                    <div className={styles.cardTitleRow}>
                      <h3 className={styles.cardTitle}>
                        {t("account.securityRecovery")}
                      </h3>
                      {hasFactor ? (
                        <Tag className={styles.statusTag} color="default">
                          {t("account.securityRecoveryCount", {
                            count: status?.recovery_remaining ?? 0,
                          })}
                        </Tag>
                      ) : null}
                    </div>
                    <p className={styles.cardDesc}>
                      {hasFactor
                        ? t("account.securityRecoveryDesc")
                        : t("account.securityRecoveryNeedFactor")}
                    </p>
                  </div>
                </div>
                <div className={styles.cardSide}>
                  {canEnroll && hasFactor ? (
                    <Button
                      disabled={busy}
                      onClick={() => requestReauth({ kind: "recovery_regen" })}
                    >
                      {t("account.securityRecoveryRegenerate")}
                    </Button>
                  ) : null}
                </div>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );

  return (
    <>
      <Drawer
        title={t("account.security")}
        open={open}
        onClose={onClose}
        placement="right"
        width={isMobile ? "100%" : 440}
        destroyOnHidden
        className={styles.drawer}
      >
        {body}
      </Drawer>

      <Modal
        title={t("account.securityReauthTitle")}
        open={reauthOpen}
        onCancel={() => setReauthOpen(false)}
        confirmLoading={busy}
        okText={t("account.securityReauthSubmit")}
        onOk={() => reauthForm.submit()}
        destroyOnHidden
      >
        <p className={styles.reauthHint}>{t("account.securityReauthHint")}</p>
        <Form
          form={reauthForm}
          layout="vertical"
          onFinish={(values) => {
            if (!reauthAction) return;
            const action =
              reauthAction.kind === "passkey_add"
                ? {
                    ...reauthAction,
                    name: (values.passkeyName ?? "").trim(),
                  }
                : reauthAction;
            void runWithReauth(values.password, action);
          }}
        >
          {reauthAction?.kind === "passkey_add" ? (
            <Form.Item
              name="passkeyName"
              label={t("account.securityPasskeyName")}
              extra={t("account.securityPasskeyNameHint")}
            >
              <Input
                placeholder={t("account.securityPasskeyNamePlaceholder")}
                maxLength={64}
                autoFocus
              />
            </Form.Item>
          ) : null}
          <Form.Item
            name="password"
            label={t("account.currentPassword")}
            rules={[
              {
                required: true,
                message: t("account.currentPasswordRequired"),
              },
            ]}
          >
            <Input.Password
              autoComplete="current-password"
              autoFocus={reauthAction?.kind !== "passkey_add"}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t("account.securityRecovery")}
        open={recoveryCodes != null}
        closable={false}
        maskClosable={false}
        footer={
          <Space>
            <Button
              onClick={() => {
                const codes = recoveryCodes ?? [];
                if (codes.length === 0) return;
                const blob = new Blob([codes.join("\n") + "\n"], {
                  type: "text/plain;charset=utf-8",
                });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "octop-recovery-codes.txt";
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              {t("account.securityRecoveryDownload")}
            </Button>
            <Button type="primary" onClick={() => setRecoveryCodes(null)}>
              {t("account.securityRecoverySaved")}
            </Button>
          </Space>
        }
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={t("account.securityRecoveryShowOnce")}
        />
        <pre className={styles.recoveryPre}>
          {(recoveryCodes ?? []).join("\n")}
        </pre>
      </Modal>
    </>
  );
}
