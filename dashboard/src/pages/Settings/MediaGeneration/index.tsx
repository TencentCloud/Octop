import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  Divider,
  Form,
  Input,
  Space,
  Switch,
  Typography,
} from "antd";
import { CheckCircle2, Images, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { mediaGenerationApi } from "../../../api/modules/mediaGeneration";
import { message } from "@/utils/antdMessage";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import tabStyles from "../AdvancedSettings/tabContent.module.less";

const { Text } = Typography;

const IMAGE_MODEL_OPTIONS = [
  {
    value: "doubao-seedream-5-0-lite-260128",
    label: "Doubao Seedream 5.0 Lite",
  },
  {
    value: "doubao-seedream-5-0-260128",
    label: "Doubao Seedream 5.0",
  },
];

const VIDEO_MODEL_OPTIONS = [
  {
    value: "doubao-seedance-2-0-mini-260615",
    label: "Doubao Seedance 2.0 Mini",
  },
  {
    value: "doubao-seedance-2-0-fast-260128",
    label: "Doubao Seedance 2.0 Fast",
  },
  {
    value: "doubao-seedance-2-0-260128",
    label: "Doubao Seedance 2.0",
  },
];

export function MediaGenerationSettingsPanel() {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingCredentials, setTestingCredentials] = useState(false);
  const [testingModel, setTestingModel] = useState<"image" | "video" | null>(
    null,
  );
  const [apiKeySet, setApiKeySet] = useState(false);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const cfg = await mediaGenerationApi.get();
      setApiKeySet(cfg.api_key_set);
      form.setFieldsValue({
        enabled: cfg.enabled,
        provider: cfg.provider,
        base_url: cfg.base_url,
        image_enabled: cfg.image_enabled,
        video_enabled: cfg.video_enabled,
        image_model: cfg.image_model,
        video_model: cfg.video_model,
        api_key: "",
      });
    } catch (err) {
      message.error(t("mediaGeneration.loadError"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [form, t]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const handleSave = async () => {
    try {
      setSaving(true);
      const values = await form.validateFields();
      const cfg = await mediaGenerationApi.save({
        enabled: Boolean(values.enabled),
        image_enabled: Boolean(values.image_enabled),
        video_enabled: Boolean(values.video_enabled),
        image_model: String(values.image_model || "").trim(),
        video_model: String(values.video_model || "").trim(),
        api_key: values.api_key ? String(values.api_key).trim() : null,
      });
      setApiKeySet(cfg.api_key_set);
      form.setFieldValue("api_key", "");
      message.success(t("mediaGeneration.saved"));
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("mediaGeneration.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleCredentialTest = async () => {
    try {
      setTestingCredentials(true);
      const draft = String(form.getFieldValue("api_key") || "").trim();
      const result = await mediaGenerationApi.test({
        kind: "credentials",
        api_key: draft || null,
      });
      if (result.ok) message.success(t("mediaGeneration.testSuccess"));
      else message.error(result.error || t("mediaGeneration.testFailed"));
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("mediaGeneration.testFailed"),
      );
    } finally {
      setTestingCredentials(false);
    }
  };

  const handleModelTest = async (kind: "image" | "video") => {
    try {
      setTestingModel(kind);
      const draft = String(form.getFieldValue("api_key") || "").trim();
      const result = await mediaGenerationApi.test({
        kind,
        api_key: draft || null,
        image_model: String(form.getFieldValue("image_model") || "").trim(),
        video_model: String(form.getFieldValue("video_model") || "").trim(),
      });
      if (result.ok) {
        message.success(
          t(
            kind === "image"
              ? "mediaGeneration.imageTestSuccess"
              : "mediaGeneration.videoTestSuccess",
          ),
        );
      } else {
        message.error(result.error || t("mediaGeneration.modelTestFailed"));
      }
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("mediaGeneration.modelTestFailed"),
      );
    } finally {
      setTestingModel(null);
    }
  };

  const enabled = Form.useWatch("enabled", form);
  const imageEnabled = Form.useWatch("image_enabled", form);
  const videoEnabled = Form.useWatch("video_enabled", form);
  const imageModel = Form.useWatch("image_model", form);
  const videoModel = Form.useWatch("video_model", form);
  const apiKey = Form.useWatch("api_key", form);

  return (
    <>
      <TabPanelHeader
        icon={<Images size={22} />}
        title={t("mediaGeneration.title")}
        description={t("mediaGeneration.description")}
      />

      {loading ? (
        <Text type="secondary">{t("mediaGeneration.loading")}</Text>
      ) : (
        <Form form={form} layout="vertical" className={tabStyles.formFields}>
          <Form.Item
            name="enabled"
            label={t("mediaGeneration.enable")}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          {enabled && (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message={t("mediaGeneration.hint")}
              />
              <Form.Item name="provider" label={t("mediaGeneration.provider")}>
                <Input disabled />
              </Form.Item>
              <Form.Item name="base_url" label={t("mediaGeneration.baseUrl")}>
                <Input disabled />
              </Form.Item>
              <Form.Item
                name="api_key"
                label={t("mediaGeneration.apiKey")}
                extra={
                  apiKeySet ? (
                    <Text type="secondary">
                      <CheckCircle2 size={12} style={{ marginRight: 4 }} />
                      {t("mediaGeneration.apiKeySet")}
                    </Text>
                  ) : null
                }
                rules={
                  apiKeySet
                    ? []
                    : [
                        {
                          required: true,
                          message: t("mediaGeneration.apiKeyRequired"),
                        },
                      ]
                }
              >
                <Input.Password
                  placeholder="ark-..."
                  autoComplete="new-password"
                />
              </Form.Item>

              <Button
                loading={testingCredentials}
                disabled={!apiKeySet && !apiKey}
                onClick={() => void handleCredentialTest()}
              >
                {t("mediaGeneration.testCredentials")}
              </Button>

              <Divider />

              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message={t("mediaGeneration.modelTestBillingHint")}
              />

              <Form.Item
                name="image_enabled"
                label={t("mediaGeneration.enableImage")}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              {imageEnabled && (
                <Form.Item
                  name="image_model"
                  label={t("mediaGeneration.imageModel")}
                  rules={[
                    {
                      required: true,
                      message: t("mediaGeneration.imageModelRequired"),
                    },
                  ]}
                >
                  <AutoComplete
                    options={IMAGE_MODEL_OPTIONS}
                    placeholder={t("mediaGeneration.customModelPlaceholder")}
                    filterOption={(input, option) =>
                      String(option?.label || "")
                        .toLowerCase()
                        .includes(input.toLowerCase()) ||
                      String(option?.value || "")
                        .toLowerCase()
                        .includes(input.toLowerCase())
                    }
                  />
                </Form.Item>
              )}
              {imageEnabled && (
                <Button
                  loading={testingModel === "image"}
                  disabled={
                    (!apiKeySet && !apiKey) || !String(imageModel || "").trim()
                  }
                  onClick={() => void handleModelTest("image")}
                >
                  {t("mediaGeneration.testImageModel")}
                </Button>
              )}

              <Form.Item
                name="video_enabled"
                label={t("mediaGeneration.enableVideo")}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              {videoEnabled && (
                <Form.Item
                  name="video_model"
                  label={t("mediaGeneration.videoModel")}
                  rules={[
                    {
                      required: true,
                      message: t("mediaGeneration.videoModelRequired"),
                    },
                  ]}
                >
                  <AutoComplete
                    options={VIDEO_MODEL_OPTIONS}
                    placeholder={t("mediaGeneration.customModelPlaceholder")}
                    filterOption={(input, option) =>
                      String(option?.label || "")
                        .toLowerCase()
                        .includes(input.toLowerCase()) ||
                      String(option?.value || "")
                        .toLowerCase()
                        .includes(input.toLowerCase())
                    }
                  />
                </Form.Item>
              )}
              {videoEnabled && (
                <Button
                  loading={testingModel === "video"}
                  disabled={
                    (!apiKeySet && !apiKey) || !String(videoModel || "").trim()
                  }
                  onClick={() => void handleModelTest("video")}
                >
                  {t("mediaGeneration.testVideoModel")}
                </Button>
              )}
            </>
          )}

          <Space>
            <Button
              type="primary"
              loading={saving}
              onClick={() => void handleSave()}
            >
              {t("common.save")}
            </Button>
            <Button
              icon={<RefreshCw size={14} />}
              onClick={() => void fetchConfig()}
            >
              {t("common.refresh")}
            </Button>
          </Space>
        </Form>
      )}
    </>
  );
}

export default MediaGenerationSettingsPanel;
