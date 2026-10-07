import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Divider,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Select,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import { Activity, Mic2, Check, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  voiceApi,
  type VoicePreset,
  type VoiceProviderInput,
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
  custom?: boolean;
}

/** Voice provider settings panel — embeddable in the Models page tab. */
export function VoiceSettingsPanel() {
  const { t } = useTranslation();
  const [presets, setPresets] = useState<VoicePreset[]>([]);
  const [providers, setProviders] = useState<VoiceProviderRow[]>([]);
  const [active, setActive] = useState({ stt: "browser", tts: "browser" });
  const [loading, setLoading] = useState(true);
  const [configure, setConfigure] = useState<ConfigureState | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [providerName, setProviderName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [sttModel, setSttModel] = useState("whisper-1");
  const [ttsModel, setTtsModel] = useState("tts-1");
  const [voiceId, setVoiceId] = useState("alloy");
  const [secretId, setSecretId] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [mimoEndpoint, setMimoEndpoint] = useState<"payg" | "tokenplan">(
    "payg",
  );
  const [mimoVoiceId, setMimoVoiceId] = useState("冰糖");
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState(false);

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

  const availablePresets = useMemo(
    () => [
      ...presets,
      ...providers
        .filter(
          (row) =>
            !presets.some((p) => p.id === row.name || p.name === row.name),
        )
        .map(
          (row): VoicePreset => ({
            id: row.name,
            name: row.name,
            kind: row.kind,
            capability: row.capability,
            free: false,
            requires_key: true,
            description: t("voice.customHint"),
          }),
        ),
    ],
    [presets, providers, t],
  );

  const sttPresets = useMemo(
    () =>
      availablePresets.filter(
        (p) => p.capability === "stt" || p.capability === "both",
      ),
    [availablePresets],
  );
  const ttsPresets = useMemo(
    () =>
      availablePresets.filter(
        (p) => p.capability === "tts" || p.capability === "both",
      ),
    [availablePresets],
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
    setConfigure({
      preset,
      existing,
      custom: !presets.some((p) => p.id === preset.id),
    });
    setProviderName(existing?.name ?? "");
    setBaseUrl(existing?.base_url ?? "https://api.openai.com/v1");
    setApiKey(existing?.api_key ?? "");
    const extra = existing?.extra ?? {};
    setSttModel(String(extra.stt_model ?? extra.model ?? "whisper-1"));
    setTtsModel(String(extra.tts_model ?? extra.model ?? "tts-1"));
    setVoiceId(String(extra.voice_id ?? "alloy"));
    setSecretId(String(extra.secret_id ?? ""));
    setSecretKey(String(extra.secret_key ?? ""));
    setMimoEndpoint(extra.endpoint_type === "tokenplan" ? "tokenplan" : "payg");
    setMimoVoiceId(String(extra.voice_id ?? "冰糖"));
  };

  const buildProviderPayload = (): VoiceProviderInput | null => {
    if (!configure) return null;
    const { preset } = configure;
    let extra: Record<string, unknown>;
    let providerBaseUrl: string | null = null;
    if (preset.kind === "tencent") {
      extra = {
        secret_id: secretId,
        secret_key: secretKey,
        region: "ap-guangzhou",
      };
    } else if (preset.kind === "edge") {
      extra = { voice_id: "zh-CN-XiaoxiaoNeural" };
    } else if (preset.kind === "mimo") {
      providerBaseUrl =
        mimoEndpoint === "tokenplan"
          ? "https://token-plan-cn.xiaomimimo.com/v1"
          : "https://api.xiaomimimo.com/v1";
      extra = {
        endpoint_type: mimoEndpoint,
        voice_id: preset.capability === "tts" ? mimoVoiceId : undefined,
      };
    } else {
      extra =
        preset.kind === "openai"
          ? {
              stt_model: sttModel.trim(),
              tts_model: ttsModel.trim(),
              voice_id: voiceId.trim(),
            }
          : {};
      if (preset.kind === "openai") providerBaseUrl = baseUrl.trim();
    }
    return {
      name: configure.custom ? providerName.trim() : preset.id,
      kind: preset.kind,
      capability: preset.capability,
      base_url: providerBaseUrl,
      api_key:
        preset.kind === "tencent"
          ? secretId && secretKey
            ? `${secretId}:${secretKey}`
            : null
          : apiKey || null,
      extra_json: JSON.stringify(extra),
    };
  };

  const validateCredentials = () => {
    if (
      configure?.custom &&
      (!providerName.trim() ||
        (!configure.existing &&
          (presets.some(
            (p) =>
              p.id === providerName.trim() || p.name === providerName.trim(),
          ) ||
            providers.some((p) => p.name === providerName.trim()))))
    ) {
      message.warning(t("voice.uniqueNameRequired"));
      return false;
    }
    if (
      configure?.preset.kind === "openai" &&
      (!/^https:\/\/[^\s]+$/.test(baseUrl.trim()) ||
        ((configure.preset.capability === "stt" ||
          configure.preset.capability === "both") &&
          !sttModel.trim()) ||
        ((configure.preset.capability === "tts" ||
          configure.preset.capability === "both") &&
          !ttsModel.trim()))
    ) {
      message.warning(t("voice.endpointModelRequired"));
      return false;
    }
    if (!configure?.preset.requires_key) return true;
    const complete =
      configure.preset.kind === "tencent"
        ? Boolean(secretId.trim() && secretKey.trim())
        : Boolean(apiKey.trim());
    if (!complete) message.warning(t("voice.credentialsRequired"));
    return complete;
  };

  const handleProbe = async () => {
    const payload = buildProviderPayload();
    if (!payload || !validateCredentials() || !configure) return;
    const modes: ("stt" | "tts")[] =
      configure.preset.capability === "both"
        ? ["stt", "tts"]
        : [configure.preset.capability];
    setProbing(true);
    try {
      for (const mode of modes) {
        const result = await voiceApi.testConfiguration({ ...payload, mode });
        if (!result.ok) {
          message.error(result.error || t("voice.probeFailed"));
          return;
        }
      }
      message.success(t("voice.probeSuccess"));
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("voice.probeFailed"),
      );
    } finally {
      setProbing(false);
    }
  };

  const handleSaveProvider = async () => {
    const payload = buildProviderPayload();
    if (!configure || !payload || !validateCredentials()) return;
    setSaving(true);
    try {
      const { preset, existing } = configure;
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
        const next = await voiceApi.setActive({ stt: payload.name });
        setActive(next);
        invalidateVoiceConfigCache();
      }
      if (
        preset.kind !== "browser" &&
        (preset.capability === "tts" || preset.capability === "both") &&
        active.tts === "browser"
      ) {
        const next = await voiceApi.setActive({ tts: payload.name });
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
              {configured && !presets.some((p) => p.id === preset.id) && (
                <Popconfirm
                  title={t("voice.deleteConfirm")}
                  onConfirm={async () => {
                    try {
                      await voiceApi.deleteProvider(configured.id);
                      await fetchAll();
                    } catch {
                      message.error(t("common.deleteFailed"));
                    }
                  }}
                >
                  <Button
                    size="small"
                    danger
                    disabled={
                      active.stt === preset.id || active.tts === preset.id
                    }
                  >
                    {t("common.delete")}
                  </Button>
                </Popconfirm>
              )}
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
        title={t("models.voiceModelsTab")}
        description={t("voice.description")}
      />

      <Button
        onClick={() =>
          openConfigure({
            id: "",
            name: t("voice.customProvider"),
            kind: "openai",
            capability: "both",
            free: false,
            requires_key: true,
            description: t("voice.customHint"),
          })
        }
      >
        {t("voice.addCustom")}
      </Button>

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

      <Drawer
        title={t("voice.configureTitle", {
          name: configure?.preset.name ?? "",
        })}
        open={!!configure}
        onClose={() => setConfigure(null)}
        width={440}
        placement="right"
        destroyOnHidden
        footer={
          <div className={styles.drawerFooter}>
            <Button onClick={() => setConfigure(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              icon={<Activity size={14} />}
              loading={probing}
              onClick={() => void handleProbe()}
            >
              {t("voice.probe")}
            </Button>
            <Button
              type="primary"
              loading={saving}
              onClick={() => void handleSaveProvider()}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        <Form layout="vertical">
          {configure?.custom && (
            <>
              <Form.Item label={t("voice.providerName")} required>
                <Input
                  value={providerName}
                  placeholder={t("voice.providerName")}
                  disabled={!!configure.existing}
                  onChange={(e) => setProviderName(e.target.value)}
                />
              </Form.Item>
              <Form.Item label={t("voice.capability")} required>
                <Select
                  value={configure.preset.capability}
                  onChange={(capability: VoicePreset["capability"]) =>
                    setConfigure({
                      ...configure,
                      preset: { ...configure.preset, capability },
                    })
                  }
                  options={[
                    { value: "stt", label: t("voice.sttSection") },
                    { value: "tts", label: t("voice.ttsSection") },
                    { value: "both", label: t("voice.both") },
                  ]}
                />
              </Form.Item>
            </>
          )}
          {configure?.preset.kind === "tencent" && (
            <>
              <div className={styles.drawerHint}>{t("voice.tencentHint")}</div>
              <Form.Item label="SecretId" required>
                <Input
                  placeholder="SecretId"
                  value={secretId}
                  onChange={(e) => setSecretId(e.target.value)}
                />
              </Form.Item>
              <Form.Item label="SecretKey" required>
                <Input.Password
                  placeholder="SecretKey"
                  value={secretKey}
                  onChange={(e) => setSecretKey(e.target.value)}
                />
              </Form.Item>
            </>
          )}
          {configure?.preset.kind === "openai" && (
            <>
              <div className={styles.drawerHint}>{t("voice.customHint")}</div>
              <Form.Item label="API Key" required>
                <Input.Password
                  placeholder="API Key"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </Form.Item>
              <Form.Item label={t("voice.mimoEndpoint")} required>
                <Input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                />
              </Form.Item>
              {configure.preset.capability !== "tts" && (
                <Form.Item label={t("voice.sttModel")} required>
                  <Input
                    value={sttModel}
                    onChange={(e) => setSttModel(e.target.value)}
                  />
                </Form.Item>
              )}
              {configure.preset.capability !== "stt" && (
                <>
                  <Form.Item label={t("voice.ttsModel")} required>
                    <Input
                      value={ttsModel}
                      onChange={(e) => setTtsModel(e.target.value)}
                    />
                  </Form.Item>
                  <Form.Item label={t("voice.mimoVoice")}>
                    <Input
                      value={voiceId}
                      onChange={(e) => setVoiceId(e.target.value)}
                    />
                  </Form.Item>
                </>
              )}
            </>
          )}
          {configure?.preset.kind === "mimo" && (
            <>
              <div className={styles.drawerHint}>{t("voice.mimoHint")}</div>
              <Form.Item label={t("voice.mimoEndpoint")} required>
                <Select
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
              </Form.Item>
              <Form.Item label="API Key" required>
                <Input.Password
                  placeholder="API Key (sk-... / tp-...)"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </Form.Item>
              {configure.preset.capability === "tts" && (
                <Form.Item label={t("voice.mimoVoice")}>
                  <Select
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
                </Form.Item>
              )}
            </>
          )}
        </Form>
      </Drawer>
    </>
  );
}

export default VoiceSettingsPanel;
