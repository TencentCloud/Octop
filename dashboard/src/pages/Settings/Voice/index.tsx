import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Divider, Modal, Space, Typography, Input, Select } from "antd";
import { message } from "@/utils/antdMessage";

import { Mic2, RefreshCw, Check, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  voiceApi,
  type VoicePreset,
  type VoiceProviderRow,
} from "../../../api/modules/voice";
import { customProviderLogo, getProviderLogo } from "../../../assets/providers";
import { invalidateVoiceConfigCache } from "../../../hooks/useVoiceConfig";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

const { Text } = Typography;

function voiceLogoForKind(kind: string): string {
  return getProviderLogo(kind) ?? customProviderLogo;
}

interface ConfigureState {
  preset: VoicePreset;
  existing?: VoiceProviderRow;
}

/** Voice provider settings panel — embeddable in Advanced Settings tab. */
export function VoiceSettingsPanel() {
  const { t } = useTranslation();
  const [presets, setPresets] = useState<VoicePreset[]>([]);
  const [providers, setProviders] = useState<VoiceProviderRow[]>([]);
  const [active, setActive] = useState({ stt: "browser", tts: "browser" });
  const [loading, setLoading] = useState(true);
  const [configure, setConfigure] = useState<ConfigureState | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [secretId, setSecretId] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [mimoEndpoint, setMimoEndpoint] = useState<"payg" | "tokenplan">(
    "payg",
  );
  const [mimoVoiceId, setMimoVoiceId] = useState("冰糖");
  const [saving, setSaving] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [presetList, rows, activeVoice] = await Promise.all([
        voiceApi.getPresets(),
        voiceApi.getProviders(),
        voiceApi.getActive(),
      ]);
      setPresets(presetList);
      setProviders(rows);
      setActive(activeVoice);
    } catch (err) {
      message.error(t("voice.loadError"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const sttPresets = useMemo(
    () =>
      presets.filter((p) => p.capability === "stt" || p.capability === "both"),
    [presets],
  );
  const ttsPresets = useMemo(
    () =>
      presets.filter((p) => p.capability === "tts" || p.capability === "both"),
    [presets],
  );

  const findConfigured = (preset: VoicePreset) =>
    providers.find((p) => p.name === preset.id || p.name === preset.name);

  const setActiveProvider = async (kind: "stt" | "tts", name: string) => {
    try {
      const next = await voiceApi.setActive(
        kind === "stt" ? { stt: name } : { tts: name },
      );
      setActive(next);
      invalidateVoiceConfigCache();
      message.success(t("voice.activeUpdated"));
    } catch {
      message.error(t("voice.activeUpdateFailed"));
    }
  };

  const openConfigure = (preset: VoicePreset) => {
    const existing = findConfigured(preset);
    setConfigure({ preset, existing });
    setApiKey(existing?.api_key ?? "");
    const extra = existing?.extra ?? {};
    setSecretId(String(extra.secret_id ?? ""));
    setSecretKey(String(extra.secret_key ?? ""));
    setMimoEndpoint(extra.endpoint_type === "tokenplan" ? "tokenplan" : "payg");
    setMimoVoiceId(String(extra.voice_id ?? "冰糖"));
  };

  const handleSaveProvider = async () => {
    if (!configure) return;
    setSaving(true);
    try {
      const { preset, existing } = configure;
      let extra: Record<string, unknown>;
      let baseUrl: string | null = null;
      if (preset.kind === "tencent") {
        extra = {
          secret_id: secretId,
          secret_key: secretKey,
          region: "ap-guangzhou",
        };
      } else if (preset.kind === "edge") {
        extra = { voice_id: "zh-CN-XiaoxiaoNeural" };
      } else if (preset.kind === "mimo") {
        const mimoBase =
          mimoEndpoint === "tokenplan"
            ? "https://token-plan-cn.xiaomimimo.com/v1"
            : "https://api.xiaomimimo.com/v1";
        baseUrl = mimoBase;
        extra = {
          endpoint_type: mimoEndpoint,
          voice_id: preset.capability === "tts" ? mimoVoiceId : undefined,
        };
      } else {
        extra = { model: preset.kind === "openai" ? "whisper-1" : undefined };
      }
      const payload = {
        name: preset.id,
        kind: preset.kind,
        capability: preset.capability,
        base_url: baseUrl,
        api_key:
          preset.kind === "tencent"
            ? secretId && secretKey
              ? `${secretId}:${secretKey}`
              : null
            : apiKey || null,
        extra_json: JSON.stringify(extra),
      };
      if (existing) {
        await voiceApi.patchProvider(existing.id, payload);
      } else {
        await voiceApi.createProvider(payload);
      }
      if (
        preset.kind !== "browser" &&
        (preset.capability === "stt" || preset.capability === "both") &&
        active.stt === "browser"
      ) {
        const next = await voiceApi.setActive({ stt: preset.id });
        setActive(next);
        invalidateVoiceConfigCache();
      }
      if (
        preset.kind !== "browser" &&
        (preset.capability === "tts" || preset.capability === "both") &&
        active.tts === "browser"
      ) {
        const next = await voiceApi.setActive({ tts: preset.id });
        setActive(next);
        invalidateVoiceConfigCache();
      }
      message.success(t("voice.saved"));
      setConfigure(null);
      await fetchAll();
    } catch {
      message.error(t("common.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const renderPresetCard = (preset: VoicePreset, kind: "stt" | "tts") => {
    const configured = findConfigured(preset);
    const isActive = active[kind] === preset.id;
    const needsSetup =
      preset.requires_key && !configured && preset.kind !== "browser";
    const logo = voiceLogoForKind(preset.kind);

    const cardClass = [
      styles.card,
      isActive ? styles.cardActive : "",
      needsSetup ? styles.cardSetup : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div
        key={`${kind}-${preset.id}`}
        className={cardClass}
        role={needsSetup ? "button" : undefined}
        tabIndex={needsSetup ? 0 : undefined}
        onClick={needsSetup ? () => openConfigure(preset) : undefined}
        onKeyDown={
          needsSetup
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  openConfigure(preset);
                }
              }
            : undefined
        }
      >
        <div className={styles.cardHeader}>
          <div className={styles.logoTile}>
            <img
              src={logo}
              alt={preset.name}
              className={styles.logo}
              draggable={false}
            />
          </div>
          <div className={styles.titleBlock}>
            <div className={styles.nameRow}>
              <span className={styles.name}>{preset.name}</span>
            </div>
            <div className={styles.kind}>{preset.kind}</div>
          </div>
          <div className={styles.badges}>
            {isActive && (
              <span className={`${styles.badge} ${styles.badgeActive}`}>
                <Check size={11} />
                {t("voice.active")}
              </span>
            )}
            {preset.free && (
              <span className={`${styles.badge} ${styles.badgeFree}`}>
                {t("voice.free")}
              </span>
            )}
            {preset.limited_free && (
              <span className={`${styles.badge} ${styles.badgeFree}`}>
                {t("voice.limitedFree")}
              </span>
            )}
            {needsSetup && (
              <span className={`${styles.badge} ${styles.badgeSetup}`}>
                {t("voice.notConfigured")}
              </span>
            )}
          </div>
        </div>

        <p className={styles.description}>{preset.description}</p>

        <div className={styles.actions}>
          {needsSetup ? (
            <Button
              size="small"
              type="primary"
              icon={<Settings2 size={14} />}
              onClick={(e) => {
                e.stopPropagation();
                openConfigure(preset);
              }}
            >
              {t("voice.configure")}
            </Button>
          ) : (
            <>
              <Button
                size="small"
                type={isActive ? "default" : "primary"}
                disabled={isActive}
                onClick={(e) => {
                  e.stopPropagation();
                  void setActiveProvider(kind, preset.id);
                }}
              >
                {isActive ? t("voice.current") : t("voice.setActive")}
              </Button>
              {preset.requires_key && configured ? (
                <Button
                  size="small"
                  icon={<Settings2 size={14} />}
                  onClick={(e) => {
                    e.stopPropagation();
                    openConfigure(preset);
                  }}
                >
                  {t("common.edit")}
                </Button>
              ) : null}
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <>
      <TabPanelHeader
        icon={<Mic2 size={22} />}
        title={t("nav.voice")}
        description={t("pageShell.voice.subtitle")}
        actions={
          <Button
            icon={<RefreshCw size={14} />}
            onClick={() => void fetchAll()}
          >
            {t("common.refresh")}
          </Button>
        }
      />

      {loading ? (
        <Text type="secondary">{t("voice.loading")}</Text>
      ) : (
        <>
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>{t("voice.sttSection")}</h3>
            <div className={styles.grid}>
              {sttPresets.map((p) => renderPresetCard(p, "stt"))}
            </div>
          </section>

          <Divider className={styles.divider} />

          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>{t("voice.ttsSection")}</h3>
            <div className={styles.grid}>
              {ttsPresets.map((p) => renderPresetCard(p, "tts"))}
            </div>
          </section>
        </>
      )}

      <Modal
        title={
          configure ? `${t("voice.configure")} — ${configure.preset.name}` : ""
        }
        open={!!configure}
        onCancel={() => setConfigure(null)}
        onOk={() => void handleSaveProvider()}
        confirmLoading={saving}
        okText={t("common.save")}
      >
        {configure?.preset.kind === "tencent" && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Text type="secondary">{t("voice.tencentHint")}</Text>
            <Input
              placeholder="SecretId"
              value={secretId}
              onChange={(e) => setSecretId(e.target.value)}
            />
            <Input.Password
              placeholder="SecretKey"
              value={secretKey}
              onChange={(e) => setSecretKey(e.target.value)}
            />
          </Space>
        )}
        {configure?.preset.kind === "openai" && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Text type="secondary">{t("voice.openaiHint")}</Text>
            <Input.Password
              placeholder="API Key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <Select
              style={{ width: "100%" }}
              defaultValue="https://api.openai.com/v1"
              disabled
              options={[
                { value: "https://api.openai.com/v1", label: "OpenAI API" },
              ]}
            />
          </Space>
        )}
        {configure?.preset.kind === "mimo" && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Text type="secondary">{t("voice.mimoHint")}</Text>
            <div>
              <div style={{ fontSize: 12, marginBottom: 4 }}>
                {t("voice.mimoEndpoint")}
              </div>
              <Select
                style={{ width: "100%" }}
                value={mimoEndpoint}
                onChange={(v) => setMimoEndpoint(v)}
                options={[
                  {
                    value: "payg",
                    label: t("voice.mimoEndpointPayg"),
                  },
                  {
                    value: "tokenplan",
                    label: t("voice.mimoEndpointTokenplan"),
                  },
                ]}
              />
            </div>
            <Input.Password
              placeholder="API Key (sk-... / tp-...)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            {configure.preset.capability === "tts" && (
              <div>
                <div style={{ fontSize: 12, marginBottom: 4 }}>
                  {t("voice.mimoVoice")}
                </div>
                <Select
                  style={{ width: "100%" }}
                  value={mimoVoiceId}
                  onChange={(v) => setMimoVoiceId(v)}
                  options={[
                    { value: "冰糖", label: "冰糖 (中文·女)" },
                    { value: "茉莉", label: "茉莉 (中文·女)" },
                    { value: "苏打", label: "苏打 (中文·男)" },
                    { value: "白桦", label: "白桦 (中文·男)" },
                    { value: "Mia", label: "Mia (EN·Female)" },
                    { value: "Chloe", label: "Chloe (EN·Female)" },
                    { value: "Milo", label: "Milo (EN·Male)" },
                    { value: "Dean", label: "Dean (EN·Male)" },
                  ]}
                />
              </div>
            )}
          </Space>
        )}
      </Modal>
    </>
  );
}

export default VoiceSettingsPanel;
