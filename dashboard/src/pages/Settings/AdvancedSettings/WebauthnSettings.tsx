import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Form, Input, Space } from "antd";
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  octopSettingsApi,
  type WebauthnSettings,
} from "../../../api/modules/settings";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "./TabPanelHeader";
import tabStyles from "./tabContent.module.less";

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
  const [rpId, setRpId] = useState("");
  const [originsText, setOriginsText] = useState("");
  const pageOrigin =
    typeof window !== "undefined" ? window.location.origin : "";

  const applyView = useCallback((next: WebauthnSettings) => {
    setRpId(next.rp_id ?? "");
    setOriginsText(originsToText(next.origins ?? []));
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

  const onSave = async () => {
    setSaving(true);
    try {
      const saved = await octopSettingsApi.putWebauthn({
        rp_id: rpId.trim() || null,
        origins: textToOrigins(originsText),
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

  return (
    <div className={tabStyles.panel}>
      <TabPanelHeader
        icon={<KeyRound size={20} />}
        title={t("advancedSettings.webauthn.title")}
        description={t("advancedSettings.webauthn.description")}
      />
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={t("advancedSettings.webauthn.localhostHint")}
      />
      <Form layout="vertical" disabled={loading || saving}>
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
        <Space wrap>
          <Button type="primary" loading={saving} onClick={() => void onSave()}>
            {t("advancedSettings.webauthn.save")}
          </Button>
          {pageOrigin ? (
            <Button onClick={onUseCurrentOrigin}>
              {t("advancedSettings.webauthn.useCurrentOrigin")}
            </Button>
          ) : null}
        </Space>
      </Form>
    </div>
  );
}
