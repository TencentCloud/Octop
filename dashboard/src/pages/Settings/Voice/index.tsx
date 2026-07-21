import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Divider,
  Modal,
  Space,
  Tag,
  Typography,
  message,
  Input,
  Select,
} from "antd";
import { Mic2, Mic, Volume2, RefreshCw, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  voiceApi,
  type VoicePreset,
  type VoiceProviderRow,
} from "../../../api/modules/voice";
import { invalidateVoiceConfigCache } from "../../../hooks/useVoiceConfig";
import modelStyles from "../Models/index.module.less";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import tabStyles from "../AdvancedSettings/tabContent.module.less";

const { Text, Paragraph } = Typography;

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
  };

  const handleSaveProvider = async () => {
    if (!configure) return;
    setSaving(true);
    try {
      const { preset, existing } = configure;
      const extra =
        preset.kind === "tencent"
          ? {
              secret_id: secretId,
              secret_key: secretKey,
              region: "ap-guangzhou",
            }
          : preset.kind === "edge"
          ? { voice_id: "zh-CN-XiaoxiaoNeural" }
          : { model: preset.kind === "openai" ? "whisper-1" : undefined };
      const payload = {
        name: preset.id,
        kind: preset.kind,
        capability: preset.capability,
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

    return (
      <Card
        key={`${kind}-${preset.id}`}
        hoverable={needsSetup}
        className={modelStyles.providerCard}
        onClick={needsSetup ? () => openConfigure(preset) : undefined}
      >
        <div className={modelStyles.cardContent}>
          <div className={modelStyles.cardHeader}>
            <span className={modelStyles.cardName}>
              {kind === "stt" ? <Mic size={18} /> : <Volume2 size={18} />}
              <span style={{ marginLeft: 8 }}>{preset.name}</span>
            </span>
            <Space size={4}>
              {preset.free && <Tag color="green">{t("voice.free")}</Tag>}
              {isActive && (
                <Tag color="blue" icon={<Check size={12} />}>
                  {t("voice.active")}
                </Tag>
              )}
              {needsSetup && <Tag>{t("voice.notConfigured")}</Tag>}
            </Space>
          </div>
          <Paragraph type="secondary" style={{ marginBottom: 8, fontSize: 13 }}>
            {preset.description}
          </Paragraph>
          <Space>
            {!needsSetup && (
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
            )}
            {preset.requires_key && configured && (
              <Button
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  openConfigure(preset);
                }}
              >
                {t("common.edit")}
              </Button>
            )}
          </Space>
        </div>
      </Card>
    );
  };

  return (
    <>
      <TabPanelHeader
        icon={<Mic2 size={22} />}
        title={t("nav.voice")}
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
          <h3 className={tabStyles.sectionTitle}>{t("voice.sttSection")}</h3>
          <div className={modelStyles.providerCards}>
            {sttPresets.map((p) => renderPresetCard(p, "stt"))}
          </div>

          <Divider />

          <h3 className={tabStyles.sectionTitle}>{t("voice.ttsSection")}</h3>
          <div className={modelStyles.providerCards}>
            {ttsPresets.map((p) => renderPresetCard(p, "tts"))}
          </div>
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
      </Modal>
    </>
  );
}

export default VoiceSettingsPanel;
