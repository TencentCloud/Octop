import { useEffect, useState } from "react";
import { Button, Drawer, Form, Input, Select } from "antd";
import { Activity } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { apiErrorMessage } from "../../../utils/apiError";
import {
  voiceApi,
  type VoiceProviderInput,
  type VoiceProviderRow,
} from "../../../api/modules/voice";
import styles from "./index.module.less";

interface CustomVoiceProviderDrawerProps {
  open: boolean;
  existing?: VoiceProviderRow;
  reservedNames: string[];
  providers: VoiceProviderRow[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}

interface ProviderFields {
  name: string;
  kind: "openai" | "dashscope";
  capability: "stt" | "tts" | "both";
  base_url: string;
  api_key?: string;
  stt_model?: string;
  tts_model?: string;
  voice_id?: string;
  note?: string;
}

const DEFAULTS = {
  openai: {
    base_url: "https://api.openai.com/v1",
    stt_model: "whisper-1",
    tts_model: "tts-1",
    voice_id: "alloy",
  },
  dashscope: {
    base_url: "https://dashscope.aliyuncs.com/api/v1",
    stt_model: "qwen3-asr-flash",
    tts_model: "qwen3-tts-flash",
    voice_id: "Cherry",
  },
};

export function CustomVoiceProviderDrawer({
  open,
  existing,
  reservedNames,
  providers,
  onClose,
  onSaved,
}: CustomVoiceProviderDrawerProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<ProviderFields>();
  const kind = Form.useWatch("kind", form);
  const capability = Form.useWatch("capability", form);
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    const providerKind =
      existing?.kind === "dashscope" ? "dashscope" : "openai";
    const defaults = DEFAULTS[providerKind];
    const extra = existing?.extra ?? {};
    form.setFieldsValue({
      name: existing?.name ?? "",
      kind: providerKind,
      capability: existing?.capability ?? "both",
      base_url: existing?.base_url ?? defaults.base_url,
      api_key: existing?.api_key ?? "",
      stt_model: String(
        extra.stt_model ??
          (existing?.capability !== "tts" ? extra.model : undefined) ??
          defaults.stt_model,
      ),
      tts_model: String(
        extra.tts_model ??
          (existing?.capability === "tts" ? extra.model : undefined) ??
          defaults.tts_model,
      ),
      voice_id: String(extra.voice_id ?? defaults.voice_id),
      note: existing?.note ?? "",
    });
  }, [open, existing, form]);

  const buildPayload = async (): Promise<VoiceProviderInput> => {
    const values = await form.validateFields();
    const extra = { ...existing?.extra };
    if (values.capability !== "tts") extra.stt_model = values.stt_model?.trim();
    if (values.capability !== "stt") {
      extra.tts_model = values.tts_model?.trim();
      extra.voice_id = values.voice_id?.trim();
    }
    return {
      name: values.name.trim(),
      kind: values.kind,
      capability: values.capability,
      base_url: values.base_url.trim(),
      api_key: values.api_key?.trim() || null,
      extra_json: JSON.stringify(extra),
      note: values.note?.trim() || null,
    };
  };

  const handleSave = async () => {
    try {
      const payload = await buildPayload();
      setSaving(true);
      if (existing) await voiceApi.patchProvider(existing.id, payload);
      else await voiceApi.createProvider(payload);
      message.success(t("voice.saved"));
      await onSaved();
      onClose();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(apiErrorMessage(err, t("common.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const handleProbe = async () => {
    try {
      const payload = await buildPayload();
      setProbing(true);
      const modes: ("stt" | "tts")[] =
        payload.capability === "both"
          ? ["stt", "tts"]
          : [payload.capability as "stt" | "tts"];
      for (const mode of modes) {
        const result = await voiceApi.testConfiguration({ ...payload, mode });
        if (!result.ok) {
          message.error(result.error || t("voice.probeFailed"));
          return;
        }
      }
      message.success(t("voice.probeSuccess"));
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(apiErrorMessage(err, t("voice.probeFailed"), t));
    } finally {
      setProbing(false);
    }
  };

  return (
    <Drawer
      title={t(
        existing ? "voice.editCustomProvider" : "voice.addCustomProvider",
      )}
      open={open}
      onClose={onClose}
      width={480}
      destroyOnHidden
      footer={
        <div className={styles.drawerFooter}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            icon={<Activity size={14} />}
            loading={probing}
            disabled={saving}
            onClick={() => void handleProbe()}
          >
            {t("voice.probe")}
          </Button>
          <Button
            type="primary"
            loading={saving}
            disabled={probing}
            onClick={() => void handleSave()}
          >
            {t("common.save")}
          </Button>
        </div>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={t("models.nameLabel")}
          rules={[
            {
              required: true,
              whitespace: true,
              message: t("models.pleaseEnterName"),
            },
            {
              validator: (_, value: string | undefined) => {
                const name = value?.trim();
                if (name && reservedNames.includes(name)) {
                  return Promise.reject(
                    new Error(t("voice.reservedProviderName")),
                  );
                }
                if (
                  providers.some(
                    (p) => p.name === name && p.id !== existing?.id,
                  )
                ) {
                  return Promise.reject(
                    new Error(t("voice.duplicateProviderName")),
                  );
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <Input
            disabled={!!existing}
            placeholder={t("voice.customNamePlaceholder")}
          />
        </Form.Item>
        <Form.Item
          name="kind"
          label={t("voice.protocol")}
          rules={[{ required: true }]}
        >
          <Select
            onChange={(value: "openai" | "dashscope") =>
              form.setFieldsValue(DEFAULTS[value])
            }
            options={[
              { value: "openai", label: t("models.kindOpenaiCompat") },
              { value: "dashscope", label: t("voice.dashscopeProtocol") },
            ]}
          />
        </Form.Item>
        <div className={styles.drawerHint}>
          {t(
            kind === "dashscope"
              ? "voice.dashscopeHint"
              : "voice.compatibilityHint",
          )}
        </div>
        <Form.Item
          name="capability"
          label={t("voice.capability")}
          rules={[{ required: true }]}
        >
          <Select
            options={[
              { value: "stt", label: t("voice.sttSection") },
              { value: "tts", label: t("voice.ttsSection") },
              { value: "both", label: t("voice.bothCapabilities") },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="base_url"
          label={t("voice.mimoEndpoint")}
          rules={[
            {
              required: true,
              whitespace: true,
              message: t("voice.endpointRequired"),
            },
            {
              type: "url",
              pattern: /^https:\/\//,
              message: t("voice.endpointInvalid"),
            },
          ]}
        >
          <Input
            placeholder={
              DEFAULTS[kind === "dashscope" ? "dashscope" : "openai"].base_url
            }
          />
        </Form.Item>
        <Form.Item
          name="api_key"
          label="API Key"
          rules={[
            {
              required: true,
              whitespace: true,
              message: t("voice.credentialsRequired"),
            },
          ]}
        >
          <Input.Password placeholder="sk-..." />
        </Form.Item>
        {capability !== "tts" && (
          <Form.Item
            name="stt_model"
            label={t("voice.sttModel")}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t("voice.modelRequired"),
              },
            ]}
          >
            <Input />
          </Form.Item>
        )}
        {capability !== "stt" && (
          <>
            <Form.Item
              name="tts_model"
              label={t("voice.ttsModel")}
              rules={[
                {
                  required: true,
                  whitespace: true,
                  message: t("voice.modelRequired"),
                },
              ]}
            >
              <Input />
            </Form.Item>
            <Form.Item name="voice_id" label={t("voice.mimoVoice")}>
              <Input placeholder={t("voice.voiceIdPlaceholder")} />
            </Form.Item>
          </>
        )}
        <Form.Item name="note" label={t("models.noteLabel")}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
