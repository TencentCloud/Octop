import { useCallback, useEffect, useState } from "react";
import { Button, Form, Input, Switch } from "antd";
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  octopSettingsApi,
  type WebauthnSettings,
} from "../../../api/modules/settings";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "./TabPanelHeader";
import styles from "./WebauthnSettings.module.less";

function originsToText(origins: string[]): string {
  return origins.join("\n");
}

function textToOrigins(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function WebauthnSettingsPanel() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingLogin, setSavingLogin] = useState(false);
  const [rpId, setRpId] = useState("");
  const [originsText, setOriginsText] = useState("");
  const [passwordlessLogin, setPasswordlessLogin] = useState(false);
  const pageOrigin =
    typeof window !== "undefined" ? window.location.origin : "";

  const applyView = useCallback((next: WebauthnSettings) => {
    setRpId(next.rp_id ?? "");
    setOriginsText(originsToText(next.origins ?? []));
    setPasswordlessLogin(next.passwordless_login === true);
  }, []);

  const load = useCallback(async () => {
    try {
      applyView(await octopSettingsApi.webauthn());
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("advancedSettings.webauthn.loadFailed"), t),
      );
    } finally {
      setLoading(false);
    }
  }, [applyView, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onPasswordlessChange = async (checked: boolean) => {
    setPasswordlessLogin(checked);
    setSavingLogin(true);
    try {
      const saved = await octopSettingsApi.putWebauthn({
        passwordless_login: checked,
      });
      setPasswordlessLogin(saved.passwordless_login === true);
      message.success(t("advancedSettings.webauthn.saved"));
    } catch (err) {
      setPasswordlessLogin(!checked);
      message.error(
        apiErrorMessage(err, t("advancedSettings.webauthn.saveFailed"), t),
      );
    } finally {
      setSavingLogin(false);
    }
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const saved = await octopSettingsApi.putWebauthn({
        rp_id: rpId.trim() || null,
        origins: textToOrigins(originsText),
        passwordless_login: passwordlessLogin,
      });
      applyView(saved);
      message.success(t("advancedSettings.webauthn.saved"));
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("advancedSettings.webauthn.saveFailed"), t),
      );
    } finally {
      setSaving(false);
    }
  };

  const onUseCurrentOrigin = () => {
    if (!pageOrigin) return;
    try {
      const host = new URL(pageOrigin).hostname;
      if (host && host !== "127.0.0.1" && host !== "::1") {
        setRpId(host);
      }
    } catch {
      /* ignore */
    }
    const lines = textToOrigins(originsText);
    if (!lines.includes(pageOrigin)) {
      setOriginsText(originsToText([...lines, pageOrigin]));
    }
  };

  const currentListed =
    pageOrigin !== "" && textToOrigins(originsText).includes(pageOrigin);
  const busy = loading || saving || savingLogin;

  return (
    <div className={styles.page}>
      <TabPanelHeader
        icon={<KeyRound size={20} />}
        title={t("advancedSettings.webauthn.title")}
        description={t("advancedSettings.webauthn.description")}
      />

      <div className={styles.stack}>
        <section className={styles.card}>
          <div className={styles.toggleRow}>
            <Switch
              checked={passwordlessLogin}
              loading={savingLogin}
              disabled={busy}
              onChange={(checked) => void onPasswordlessChange(checked)}
            />
            <div className={styles.toggleCopy}>
              <p className={styles.toggleLabel}>
                {t("advancedSettings.webauthn.passwordlessLogin")}
              </p>
              <p className={styles.toggleHint}>
                {t("advancedSettings.webauthn.passwordlessLoginHint")}
              </p>
            </div>
          </div>
        </section>

        <section className={styles.card}>
          <h3 className={styles.sectionTitle}>
            {t("advancedSettings.webauthn.siteTitle")}
          </h3>
          <p className={styles.sectionHint}>
            {t("advancedSettings.webauthn.localhostHint")}
          </p>
          {pageOrigin ? (
            <div className={styles.originBar}>
              <div className={styles.originMeta}>
                <span className={styles.originLabel}>
                  {t("advancedSettings.webauthn.currentOrigin")}
                </span>
                <span className={styles.originValue}>{pageOrigin}</span>
              </div>
              {currentListed ? (
                <span className={styles.originListed}>
                  {t("advancedSettings.webauthn.originListed")}
                </span>
              ) : (
                <Button disabled={busy} onClick={onUseCurrentOrigin}>
                  {t("advancedSettings.webauthn.useCurrentOrigin")}
                </Button>
              )}
            </div>
          ) : null}
          <Form className={styles.fields} layout="vertical" disabled={busy}>
            <Form.Item
              label={t("advancedSettings.webauthn.rpId")}
              extra={t("advancedSettings.webauthn.rpIdHint")}
            >
              <Input
                value={rpId}
                onChange={(e) => setRpId(e.target.value)}
                placeholder={t("advancedSettings.webauthn.rpIdPlaceholder")}
                autoComplete="off"
              />
            </Form.Item>
            <Form.Item
              label={t("advancedSettings.webauthn.origins")}
              extra={t("advancedSettings.webauthn.originsHint")}
            >
              <Input.TextArea
                value={originsText}
                onChange={(e) => setOriginsText(e.target.value)}
                placeholder={t("advancedSettings.webauthn.originsPlaceholder")}
                rows={4}
                autoComplete="off"
              />
            </Form.Item>
          </Form>
          <Button
            type="primary"
            loading={saving}
            disabled={loading || savingLogin}
            onClick={() => void onSave()}
          >
            {t("advancedSettings.webauthn.save")}
          </Button>
        </section>
      </div>
    </div>
  );
}
