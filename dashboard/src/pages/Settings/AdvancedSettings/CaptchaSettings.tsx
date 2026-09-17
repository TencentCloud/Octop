import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Input, Modal, Select } from "antd";
import { ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  octopSettingsApi,
  type CaptchaSettings,
} from "../../../api/modules/settings";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "./TabPanelHeader";
import tabStyles from "./tabContent.module.less";

export default function CaptchaSettingsPanel() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [view, setView] = useState<CaptchaSettings | null>(null);
  const [active, setActive] = useState("slider");
  const [siteKey, setSiteKey] = useState("");
  const [secret, setSecret] = useState("");
  const [camId, setCamId] = useState("");
  const [camSecret, setCamSecret] = useState("");

  const applyView = useCallback((next: CaptchaSettings) => {
    setView(next);
    setActive(next.active);
    const pair = next.providers[next.active];
    setSiteKey(pair?.site_key ?? "");
    setSecret("");
    setCamId(pair?.cam_secret_id ?? "");
    setCamSecret("");
  }, []);

  const load = useCallback(async () => {
    try {
      applyView(await octopSettingsApi.captcha());
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("advancedSettings.captcha.loadFailed"), t),
      );
    } finally {
      setLoading(false);
    }
  }, [applyView, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onActiveChange = (next: string) => {
    setActive(next);
    const pair = view?.providers[next];
    setSiteKey(pair?.site_key ?? "");
    setSecret("");
    setCamId(pair?.cam_secret_id ?? "");
    setCamSecret("");
  };

  const persist = async () => {
    setSaving(true);
    try {
      const providers =
        active === "slider"
          ? undefined
          : {
              [active]: {
                site_key: siteKey,
                ...(secret ? { secret } : {}),
                ...(active === "tencent" && camId
                  ? { cam_secret_id: camId }
                  : {}),
                ...(active === "tencent" && camSecret
                  ? { cam_secret: camSecret }
                  : {}),
              },
            };
      const saved = await octopSettingsApi.putCaptcha({ active, providers });
      applyView(saved);
      message.success(t("advancedSettings.captcha.saved"));
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("advancedSettings.captcha.saveFailed"), t),
      );
    } finally {
      setSaving(false);
    }
  };

  const onSave = () => {
    const switchingToStrong = active !== "slider" && active !== view?.active;
    if (!switchingToStrong) {
      void persist();
      return;
    }
    Modal.confirm({
      title: t("advancedSettings.captcha.confirmStrongTitle"),
      content: t("advancedSettings.captcha.confirmStrong"),
      onOk: () => persist(),
    });
  };

  const unknownActive = Boolean(
    view && active && !view.available.includes(active),
  );

  const siteKeyLabel = t(`advancedSettings.captcha.fields.${active}.siteKey`, {
    defaultValue: t("advancedSettings.captcha.siteKey"),
  });
  const secretLabel = t(`advancedSettings.captcha.fields.${active}.secret`, {
    defaultValue: t("advancedSettings.captcha.secret"),
  });

  return (
    <div>
      <TabPanelHeader
        icon={<ShieldCheck size={20} />}
        title={t("advancedSettings.captcha.title")}
        description={t("advancedSettings.captcha.description")}
      />
      {unknownActive ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("advancedSettings.captcha.unknownActive")}
        />
      ) : null}
      <div className={tabStyles.formFields}>
        <div style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 8 }}>
            {t("advancedSettings.captcha.active")}
          </div>
          <Select
            style={{ width: "100%" }}
            value={view?.available.includes(active) ? active : undefined}
            placeholder={t("advancedSettings.captcha.unknownActive")}
            loading={loading}
            onChange={onActiveChange}
            options={(view?.available ?? []).map((slug) => ({
              value: slug,
              label: t(`advancedSettings.captcha.providers.${slug}`, {
                defaultValue: slug,
              }),
            }))}
          />
        </div>
        {active !== "slider" ? (
          <>
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 8 }}>{siteKeyLabel}</div>
              <Input
                value={siteKey}
                onChange={(e) => setSiteKey(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 8 }}>{secretLabel}</div>
              <Input.Password
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder={
                  view?.providers[active]?.has_secret
                    ? t("advancedSettings.captcha.secretPlaceholder")
                    : undefined
                }
                autoComplete="new-password"
              />
            </div>
            {active === "tencent" ? (
              <>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8 }}>
                    {t("advancedSettings.captcha.camSecretId")}
                  </div>
                  <Input
                    value={camId}
                    onChange={(e) => setCamId(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8 }}>
                    {t("advancedSettings.captcha.camSecret")}
                  </div>
                  <Input.Password
                    value={camSecret}
                    onChange={(e) => setCamSecret(e.target.value)}
                    placeholder={
                      view?.providers[active]?.has_cam_secret
                        ? t("advancedSettings.captcha.secretPlaceholder")
                        : undefined
                    }
                    autoComplete="new-password"
                  />
                </div>
                <div
                  style={{
                    marginBottom: 16,
                    color: "var(--fn-text-tertiary)",
                  }}
                >
                  {t("advancedSettings.captcha.camHint")}
                </div>
              </>
            ) : null}
          </>
        ) : null}
        {view ? (
          <div style={{ marginBottom: 16, color: "var(--fn-text-tertiary)" }}>
            {t("advancedSettings.captcha.source")}:{" "}
            {t(
              `advancedSettings.captcha.source${
                view.source === "env" ? "Env" : "Settings"
              }`,
            )}
            {active === "recaptcha-v3" ? (
              <>
                {" · "}
                {t("advancedSettings.captcha.v3MinScore")}: {view.v3_min_score}
              </>
            ) : null}
          </div>
        ) : null}
        <Button type="primary" loading={saving || loading} onClick={onSave}>
          {t("advancedSettings.captcha.save")}
        </Button>
      </div>
    </div>
  );
}
