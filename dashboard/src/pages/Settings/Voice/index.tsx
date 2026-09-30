import { useCallback, useEffect, useMemo, useState } from "react";
import {
  App,
  Button,
  Divider,
  Drawer,
  Form,
  Input,
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
}

/** Voice provider settings panel — embeddable in the Models page tab. */
export function VoiceSettingsPanel() {
  const { t } = useTranslation();
  const { modal } = App.useApp();
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
    // ★ 不回填密钥：API 不再回显 `api_key`，且回填会把「已掩码/占位」的值写回库。
    //   表单固定为空 ⇒ 留空 = 保留库中原值（见 buildProviderPayload）。
    setApiKey("");
    const extra = existing?.extra ?? {};
    // ★ Tencent 的 secret_id/secret_key 副本仍在 `extra` 中（本批未掩码的已登记面），
    //   故保留回填 —— 否则保存会把 extra_json 里的副本清掉。
    setSecretId(String(extra.secret_id ?? ""));
    setSecretKey(String(extra.secret_key ?? ""));
    setMimoEndpoint(extra.endpoint_type === "tokenplan" ? "tokenplan" : "payg");
    setMimoVoiceId(String(extra.voice_id ?? "冰糖"));
  };

  /** 表单里当前的凭证输入（Tencent 拼成 `secretId:secretKey`）；空串 = 用户留空。 */
  const credentialInput = (): string => {
    if (!configure) return "";
    return configure.preset.kind === "tencent"
      ? secretId.trim() && secretKey.trim()
        ? `${secretId}:${secretKey}`
        : ""
      : apiKey.trim();
  };

  /** 已配置（`api_key_set`）⇒ 允许留空保存 —— 留空 = 保留原值。 */
  const canKeepExistingKey = (): boolean =>
    Boolean(configure?.existing?.api_key_set) && !credentialInput();

  const buildProviderPayload = (
    opts: { clearApiKey?: boolean } = {},
  ): VoiceProviderInput | null => {
    if (!configure) return null;
    const { preset } = configure;
    const clearing = opts.clearApiKey === true;
    let extra: Record<string, unknown>;
    let baseUrl: string | null = null;
    if (preset.kind === "tencent") {
      extra = {
        // ★ 显式「清除密钥」时，连同 `extra` 里的凭证副本一并清掉
        //   （`api_key` 与 `extra.secret_*` 是同一份凭证的两个落点）。
        secret_id: clearing ? "" : secretId,
        secret_key: clearing ? "" : secretKey,
        region: "ap-guangzhou",
      };
    } else if (preset.kind === "edge") {
      extra = { voice_id: "zh-CN-XiaoxiaoNeural" };
    } else if (preset.kind === "mimo") {
      baseUrl =
        mimoEndpoint === "tokenplan"
          ? "https://token-plan-cn.xiaomimimo.com/v1"
          : "https://api.xiaomimimo.com/v1";
      extra = {
        endpoint_type: mimoEndpoint,
        voice_id: preset.capability === "tts" ? mimoVoiceId : undefined,
      };
    } else {
      extra = { model: preset.kind === "openai" ? "whisper-1" : undefined };
    }
    const payload: VoiceProviderInput = {
      name: preset.id,
      kind: preset.kind,
      capability: preset.capability,
      base_url: baseUrl,
      extra_json: JSON.stringify(extra),
    };
    // ★ 三态：显式 `null` ⇒ 清空 · 非空 ⇒ 覆盖 · **省略** ⇒ 保留。
    if (clearing) payload.api_key = null;
    else if (credentialInput()) payload.api_key = credentialInput();
    return payload;
  };

  const validateCredentials = (allowKeepExisting = false) => {
    if (!configure?.preset.requires_key) return true;
    const complete = Boolean(credentialInput());
    if (complete) return true;
    if (allowKeepExisting && canKeepExistingKey()) return true;
    message.warning(t("voice.credentialsRequired"));
    return false;
  };

  const handleProbe = async () => {
    const payload = buildProviderPayload();
    if (!payload || !configure) return;
    // ★ 已配置 + 表单留空 ⇒ 用【已存密钥】探测（不再要求重填；明文已不回显）。
    const probeStored =
      canKeepExistingKey() && Boolean(configure.existing) && !credentialInput();
    if (!probeStored && !validateCredentials()) return;
    const modes: ("stt" | "tts")[] =
      configure.preset.capability === "both"
        ? ["stt", "tts"]
        : [configure.preset.capability];
    setProbing(true);
    try {
      for (const mode of modes) {
        const result = probeStored
          ? await voiceApi.testProvider(configure.existing!.id, mode)
          : await voiceApi.testConfiguration({ ...payload, mode });
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
    // ★ 硬阻塞解除：已配置（`api_key_set`）⇒ 允许留空保存（留空 = 保留原值）。
    if (!configure || !payload || !validateCredentials(true)) return;
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

  /** ★ 显式「清除密钥」：既存密钥无法移除 ⇒ 安全动作缺失（本批补齐）。 */
  const handleClearApiKey = () => {
    const existing = configure?.existing;
    if (!existing) return;
    const payload = buildProviderPayload({ clearApiKey: true });
    modal.confirm({
      title: t("voice.clearApiKey"),
      content: t("voice.clearApiKeyConfirm", { name: existing.name }),
      okText: t("voice.clearApiKey"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await voiceApi.patchProvider(existing.id, {
            api_key: null,
            ...(payload?.extra_json ? { extra_json: payload.extra_json } : {}),
          });
          invalidateVoiceConfigCache();
          message.success(t("voice.clearApiKeyDone"));
          setConfigure(null);
          await fetchAll();
        } catch {
          message.error(t("voice.clearApiKeyFailed"));
        }
      },
    });
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

  /** ★ 已配置 ⇒ 留空 = 保留原值（占位文案明示，避免用户以为必须重填）。 */
  const keepKeyPlaceholder = configure?.existing?.api_key_set
    ? t("voice.apiKeyKeepPlaceholder")
    : undefined;

  return (
    <>
      <TabPanelHeader
        icon={<Mic2 size={22} />}
        title={t("models.voiceModelsTab")}
        description={t("voice.description")}
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
            {configure?.existing?.api_key_set && (
              <Button danger onClick={handleClearApiKey}>
                {t("voice.clearApiKey")}
              </Button>
            )}
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
          {configure?.existing?.api_key_set && (
            <div className={styles.drawerHint}>
              <Text type="secondary">
                <Check size={12} style={{ marginRight: 4 }} />
                {t("voice.apiKeySet")}
              </Text>
            </div>
          )}
          {configure?.preset.kind === "tencent" && (
            <>
              <div className={styles.drawerHint}>{t("voice.tencentHint")}</div>
              <Form.Item label="SecretId" required>
                <Input
                  placeholder={keepKeyPlaceholder ?? "SecretId"}
                  value={secretId}
                  onChange={(e) => setSecretId(e.target.value)}
                />
              </Form.Item>
              <Form.Item label="SecretKey" required>
                <Input.Password
                  placeholder={keepKeyPlaceholder ?? "SecretKey"}
                  value={secretKey}
                  onChange={(e) => setSecretKey(e.target.value)}
                />
              </Form.Item>
            </>
          )}
          {configure?.preset.kind === "openai" && (
            <>
              <div className={styles.drawerHint}>{t("voice.openaiHint")}</div>
              <Form.Item label="API Key" required>
                <Input.Password
                  placeholder={keepKeyPlaceholder ?? "API Key"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </Form.Item>
              <Form.Item label={t("voice.mimoEndpoint")}>
                <Select
                  value="https://api.openai.com/v1"
                  disabled
                  options={[
                    {
                      value: "https://api.openai.com/v1",
                      label: "OpenAI API",
                    },
                  ]}
                />
              </Form.Item>
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
                  placeholder={
                    keepKeyPlaceholder ?? "API Key (sk-... / tp-...)"
                  }
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
