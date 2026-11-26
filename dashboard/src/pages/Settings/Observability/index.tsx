import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  Form,
  Input,
  Radio,
  Segmented,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  Activity,
  CheckCircle2,
  CloudUpload,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  observabilityApi,
  type ClsApplicationItem,
} from "../../../api/modules/observability";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import tabStyles from "../AdvancedSettings/tabContent.module.less";

const { Text } = Typography;

type ObservabilityProvider = "cls" | "langfuse";
type ClsAppMode = "create" | "existing";

const CLS_REGION_OPTIONS = [
  { value: "ap-guangzhou", label: "ap-guangzhou (广州)" },
  { value: "ap-shanghai", label: "ap-shanghai (上海)" },
  { value: "ap-beijing", label: "ap-beijing (北京)" },
  { value: "ap-nanjing", label: "ap-nanjing (南京)" },
  { value: "ap-chengdu", label: "ap-chengdu (成都)" },
  { value: "ap-chongqing", label: "ap-chongqing (重庆)" },
  { value: "ap-hongkong", label: "ap-hongkong (香港)" },
  { value: "ap-singapore", label: "ap-singapore (新加坡)" },
  { value: "ap-tokyo", label: "ap-tokyo (东京)" },
  { value: "ap-seoul", label: "ap-seoul (首尔)" },
  { value: "na-siliconvalley", label: "na-siliconvalley (硅谷)" },
  { value: "na-ashburn", label: "na-ashburn (弗吉尼亚)" },
  { value: "eu-frankfurt", label: "eu-frankfurt (法兰克福)" },
];

/** Langfuse & Tencent Cloud CLS observability settings — embeddable in Advanced Settings tab. */
export function ObservabilitySettingsPanel() {
  const { t } = useTranslation();
  const [langfuseForm] = Form.useForm();
  const [clsForm] = Form.useForm();

  const [provider, setProvider] = useState<ObservabilityProvider>("cls");
  const [providerInitialized, setProviderInitialized] = useState(false);
  const [activeBackend, setActiveBackend] = useState<string>("none");
  const [loading, setLoading] = useState(true);

  // Langfuse state
  const [savingLangfuse, setSavingLangfuse] = useState(false);
  const [testingLangfuse, setTestingLangfuse] = useState(false);
  const [langfuseSecretSet, setLangfuseSecretSet] = useState(false);

  // CLS state
  const [savingCls, setSavingCls] = useState(false);
  const [testingCls, setTestingCls] = useState(false);
  const [creatingClsApp, setCreatingClsApp] = useState(false);
  const [fetchingClsApps, setFetchingClsApps] = useState(false);
  const [clsSecretIdSet, setClsSecretIdSet] = useState(false);
  const [clsSecretIdMasked, setClsSecretIdMasked] = useState("");
  const [clsSecretKeySet, setClsSecretKeySet] = useState(false);
  const [clsAppMode, setClsAppMode] = useState<ClsAppMode>("create");
  const [clsApps, setClsApps] = useState<ClsApplicationItem[]>([]);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const [lfCfg, clsCfg] = await Promise.all([
        observabilityApi.getLangfuse(),
        observabilityApi.getCls(),
      ]);

      setLangfuseSecretSet(lfCfg.secret_key_set);
      langfuseForm.setFieldsValue({
        enabled: lfCfg.enabled,
        public_key: lfCfg.public_key,
        host: lfCfg.host,
        secret_key: "",
      });

      setClsSecretIdSet(clsCfg.secret_id_set);
      setClsSecretIdMasked(clsCfg.secret_id_masked);
      setClsSecretKeySet(clsCfg.secret_key_set);
      setActiveBackend(clsCfg.active_backend || "none");
      clsForm.setFieldsValue({
        enabled: clsCfg.enabled,
        region: clsCfg.region || "ap-guangzhou",
        topic_id: clsCfg.topic_id || "",
        application_id: clsCfg.application_id || "",
        application_name: clsCfg.application_name || "octop",
        access_type: clsCfg.access_type || "Langfuse",
        use_internal_endpoint: clsCfg.use_internal_endpoint,
        mask_content: clsCfg.mask_content,
        logset_id: "",
        secret_id: "",
        secret_key: "",
      });
      if (clsCfg.topic_id) {
        setClsAppMode("existing");
      }

      if (!providerInitialized) {
        if (clsCfg.enabled || clsCfg.active_backend === "cls") {
          setProvider("cls");
        } else if (lfCfg.enabled || clsCfg.active_backend === "langfuse") {
          setProvider("langfuse");
        } else {
          setProvider("cls");
        }
        setProviderInitialized(true);
      }
    } catch (err) {
      message.error(t("observability.loadError"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [clsForm, langfuseForm, providerInitialized, t]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  // ── Langfuse handlers ───────────────────────────────────────────────

  const handleSaveLangfuse = async () => {
    try {
      setSavingLangfuse(true);
      const values = await langfuseForm.validateFields();
      const payload = {
        enabled: Boolean(values.enabled),
        public_key: String(values.public_key || "").trim(),
        host: String(values.host || "").trim(),
        secret_key: values.secret_key ? String(values.secret_key) : null,
      };
      const cfg = await observabilityApi.saveLangfuse(payload);
      setLangfuseSecretSet(cfg.secret_key_set);
      langfuseForm.setFieldValue("secret_key", "");
      message.success(t("observability.saved"));
      await fetchConfig();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("observability.saveFailed"),
      );
    } finally {
      setSavingLangfuse(false);
    }
  };

  const handleTestLangfuse = async () => {
    try {
      setTestingLangfuse(true);
      const values = langfuseForm.getFieldsValue();
      const result = await observabilityApi.testLangfuse({
        public_key: values.public_key || null,
        host: values.host || null,
        secret_key: values.secret_key || null,
      });
      if (result.ok) {
        message.success(t("observability.testSuccess"));
      } else {
        message.error(result.error || t("observability.testFailed"));
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("observability.testFailed"),
      );
    } finally {
      setTestingLangfuse(false);
    }
  };

  // ── CLS handlers ────────────────────────────────────────────────────

  const handleCreateClsApp = async () => {
    try {
      setCreatingClsApp(true);
      const values = clsForm.getFieldsValue();
      const appName = String(values.application_name || "").trim() || "octop";
      const result = await observabilityApi.createClsApplication({
        region: String(values.region || "").trim() || null,
        application_name: appName,
        access_type: String(values.access_type || "Langfuse"),
        logset_id: values.logset_id ? String(values.logset_id).trim() : null,
        reuse_existing: true,
        secret_id: values.secret_id ? String(values.secret_id).trim() : null,
        secret_key: values.secret_key ? String(values.secret_key).trim() : null,
      });
      clsForm.setFieldsValue({
        topic_id: result.topic_id,
        application_id: result.application_id,
        application_name: result.application_name,
        access_type: result.access_type,
      });
      if (result.created) {
        message.success(
          t("observability.clsAppCreated", { topicId: result.topic_id }),
        );
      } else {
        message.success(
          t("observability.clsAppReused", { topicId: result.topic_id }),
        );
      }
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("observability.clsCreateAppFailed"),
      );
    } finally {
      setCreatingClsApp(false);
    }
  };

  const handleFetchClsApps = async () => {
    try {
      setFetchingClsApps(true);
      const values = clsForm.getFieldsValue();
      const res = await observabilityApi.listClsApplications({
        region: String(values.region || "").trim() || null,
        secret_id: values.secret_id ? String(values.secret_id).trim() : null,
        secret_key: values.secret_key ? String(values.secret_key).trim() : null,
      });
      setClsApps(res.applications);
      if (res.applications.length === 0) {
        message.info(t("observability.clsNoAppsFound"));
      }
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("observability.clsFetchAppsFailed"),
      );
    } finally {
      setFetchingClsApps(false);
    }
  };

  const handleSelectExistingClsApp = (appId: string) => {
    const found = clsApps.find((item) => item.application_id === appId);
    if (!found) return;
    clsForm.setFieldsValue({
      application_id: found.application_id,
      application_name: found.application_name,
      access_type: found.access_type || "Langfuse",
      topic_id: found.topic_id,
    });
  };

  const handleSaveCls = async () => {
    try {
      setSavingCls(true);
      const values = await clsForm.validateFields();
      const topicId = String(values.topic_id || "").trim();
      const autoCreate =
        Boolean(values.enabled) && clsAppMode === "create" && !topicId;

      const cfg = await observabilityApi.saveCls({
        enabled: Boolean(values.enabled),
        region: String(values.region || "").trim(),
        topic_id: topicId,
        application_id: String(values.application_id || "").trim(),
        application_name:
          String(values.application_name || "").trim() || "octop",
        access_type: String(values.access_type || "Langfuse"),
        use_internal_endpoint: Boolean(values.use_internal_endpoint),
        mask_content: Boolean(values.mask_content),
        secret_id: values.secret_id ? String(values.secret_id).trim() : null,
        secret_key: values.secret_key ? String(values.secret_key).trim() : null,
        auto_create_app: autoCreate,
        logset_id: values.logset_id ? String(values.logset_id).trim() : null,
        reuse_existing: true,
      });
      setClsSecretIdSet(cfg.secret_id_set);
      setClsSecretIdMasked(cfg.secret_id_masked);
      setClsSecretKeySet(cfg.secret_key_set);
      setActiveBackend(cfg.active_backend || "none");
      clsForm.setFieldsValue({
        topic_id: cfg.topic_id,
        application_id: cfg.application_id,
        secret_id: "",
        secret_key: "",
      });
      if (cfg.application_created) {
        message.success(
          t("observability.clsSavedWithCreate", { topicId: cfg.topic_id }),
        );
      } else {
        message.success(t("observability.clsSaved"));
      }
      await fetchConfig();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("observability.saveFailed"),
      );
    } finally {
      setSavingCls(false);
    }
  };

  const handleTestCls = async () => {
    try {
      setTestingCls(true);
      const values = clsForm.getFieldsValue();
      const result = await observabilityApi.testCls({
        region: String(values.region || "").trim() || null,
        topic_id: values.topic_id ? String(values.topic_id).trim() : "",
        use_internal_endpoint: Boolean(values.use_internal_endpoint),
        secret_id: values.secret_id ? String(values.secret_id).trim() : null,
        secret_key: values.secret_key ? String(values.secret_key).trim() : null,
      });
      if (result.ok) {
        if (result.api_ok === null && result.otlp_ok) {
          message.success(t("observability.clsTestSuccessPushOnly"));
        } else {
          message.success(t("observability.clsTestSuccess"));
        }
      } else {
        message.error(result.error || t("observability.clsTestFailed"));
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("observability.clsTestFailed"),
      );
    } finally {
      setTestingCls(false);
    }
  };

  const langfuseEnabled = Form.useWatch("enabled", langfuseForm);
  const clsEnabled = Form.useWatch("enabled", clsForm);
  const clsRegion = Form.useWatch("region", clsForm) || "ap-guangzhou";
  const clsInternal = Form.useWatch("use_internal_endpoint", clsForm);
  const clsBoundAppId = Form.useWatch("application_id", clsForm);
  const clsEndpointPreview = `https://${
    String(clsRegion).trim() || "ap-guangzhou"
  }.${clsInternal ? "cls.tencentyun.com" : "cls.tencentcs.com"}/v1/traces`;

  return (
    <>
      <TabPanelHeader
        icon={<Activity size={22} />}
        title={t("observability.title")}
        description={t("observability.description")}
      />

      {loading ? (
        <Text type="secondary">{t("observability.loading")}</Text>
      ) : (
        <>
          {activeBackend === "cls_env" && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message={t("observability.envFallbackBanner")}
            />
          )}

          <div style={{ marginBottom: 20 }}>
            <Segmented<ObservabilityProvider>
              value={provider}
              onChange={(val) => setProvider(val)}
              options={[
                {
                  value: "cls",
                  label: (
                    <Space size={6}>
                      <CloudUpload size={14} />
                      <span>{t("observability.clsTitle")}</span>
                      {activeBackend === "cls" && (
                        <Tag color="green" style={{ marginInlineEnd: 0 }}>
                          {t("observability.activeTag")}
                        </Tag>
                      )}
                    </Space>
                  ),
                },
                {
                  value: "langfuse",
                  label: (
                    <Space size={6}>
                      <Activity size={14} />
                      <span>{t("observability.langfuseTitle")}</span>
                      {activeBackend === "langfuse" && (
                        <Tag color="green" style={{ marginInlineEnd: 0 }}>
                          {t("observability.activeTag")}
                        </Tag>
                      )}
                    </Space>
                  ),
                },
              ]}
            />
          </div>

          {provider === "cls" ? (
            <Form
              form={clsForm}
              layout="vertical"
              className={tabStyles.formFields}
            >
              <Form.Item
                name="enabled"
                label={t("observability.clsEnable")}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>

              {clsEnabled && (
                <>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={t("observability.clsHint")}
                  />

                  <Form.Item
                    name="region"
                    label={t("observability.clsRegion")}
                    rules={[
                      {
                        required: true,
                        message: t("observability.clsRegionRequired"),
                      },
                    ]}
                  >
                    <AutoComplete
                      options={CLS_REGION_OPTIONS}
                      placeholder="ap-guangzhou"
                      filterOption={(inputValue, option) =>
                        String(option?.label || "")
                          .toLowerCase()
                          .includes(inputValue.toLowerCase()) ||
                        String(option?.value || "")
                          .toLowerCase()
                          .includes(inputValue.toLowerCase())
                      }
                    />
                  </Form.Item>

                  <Form.Item
                    name="secret_id"
                    label={t("observability.clsSecretId")}
                    extra={
                      clsSecretIdSet ? (
                        <Text type="secondary">
                          <CheckCircle2 size={12} style={{ marginRight: 4 }} />
                          {t("observability.clsSecretIdSet", {
                            masked: clsSecretIdMasked || "****",
                          })}
                        </Text>
                      ) : null
                    }
                    rules={
                      clsSecretIdSet
                        ? []
                        : [
                            {
                              required: true,
                              message: t("observability.clsSecretIdRequired"),
                            },
                          ]
                    }
                  >
                    <Input placeholder="AKID..." autoComplete="off" />
                  </Form.Item>

                  <Form.Item
                    name="secret_key"
                    label={t("observability.clsSecretKey")}
                    extra={
                      clsSecretKeySet ? (
                        <Text type="secondary">
                          <CheckCircle2 size={12} style={{ marginRight: 4 }} />
                          {t("observability.clsSecretKeySet")}
                        </Text>
                      ) : null
                    }
                    rules={
                      clsSecretKeySet
                        ? []
                        : [
                            {
                              required: true,
                              message: t("observability.clsSecretKeyRequired"),
                            },
                          ]
                    }
                  >
                    <Input.Password
                      placeholder="SecretKey"
                      autoComplete="new-password"
                    />
                  </Form.Item>

                  <Form.Item label={t("observability.clsMode")}>
                    <Radio.Group
                      value={clsAppMode}
                      onChange={(e) => setClsAppMode(e.target.value)}
                      optionType="button"
                      buttonStyle="solid"
                      options={[
                        {
                          value: "create",
                          label: t("observability.clsModeCreate"),
                        },
                        {
                          value: "existing",
                          label: t("observability.clsModeExisting"),
                        },
                      ]}
                    />
                  </Form.Item>

                  <Form.Item
                    name="application_name"
                    label={t("observability.clsAppName")}
                    rules={[
                      {
                        required: true,
                        message: t("observability.clsAppNameRequired"),
                      },
                      {
                        validator: (_, val: string) => {
                          const s = String(val || "").trim();
                          if (s.includes("|") || s.length > 64) {
                            return Promise.reject(
                              new Error(t("observability.clsAppNameInvalid")),
                            );
                          }
                          return Promise.resolve();
                        },
                      },
                    ]}
                  >
                    <Input placeholder="octop" />
                  </Form.Item>

                  <Form.Item
                    name="access_type"
                    label={t("observability.clsAccessType")}
                  >
                    <Select
                      options={[
                        {
                          value: "Langfuse",
                          label: t("observability.clsAccessTypeLangfuse"),
                        },
                        {
                          value: "Agent",
                          label: t("observability.clsAccessTypeAgent"),
                        },
                      ]}
                    />
                  </Form.Item>

                  {clsAppMode === "create" ? (
                    <>
                      <Form.Item
                        name="logset_id"
                        label={t("observability.clsLogsetId")}
                      >
                        <Input
                          placeholder={t(
                            "observability.clsLogsetIdPlaceholder",
                          )}
                        />
                      </Form.Item>
                      <Form.Item>
                        <Button
                          icon={<Plus size={14} />}
                          loading={creatingClsApp}
                          onClick={() => void handleCreateClsApp()}
                        >
                          {t("observability.clsCreateApp")}
                        </Button>
                      </Form.Item>
                    </>
                  ) : (
                    <Form.Item label={t("observability.clsSelectExistingApp")}>
                      <Space.Compact style={{ width: "100%" }}>
                        <Select
                          style={{ width: "100%" }}
                          placeholder={t(
                            "observability.clsSelectExistingPlaceholder",
                          )}
                          value={clsBoundAppId || undefined}
                          onChange={handleSelectExistingClsApp}
                          allowClear
                          options={clsApps.map((app) => ({
                            value: app.application_id,
                            label: `${app.application_name} (${app.access_type}) — ${app.topic_id}`,
                          }))}
                        />
                        <Button
                          icon={<Search size={14} />}
                          loading={fetchingClsApps}
                          onClick={() => void handleFetchClsApps()}
                        >
                          {t("observability.clsFetchApps")}
                        </Button>
                      </Space.Compact>
                    </Form.Item>
                  )}

                  <Form.Item
                    name="topic_id"
                    label={t("observability.clsTopicId")}
                    extra={
                      <Space direction="vertical" size={2}>
                        <Text type="secondary">
                          {t("observability.clsTopicIdExtra")}
                        </Text>
                        {clsBoundAppId && (
                          <Text type="secondary">
                            {t("observability.clsApplicationId")}:{" "}
                            <Text code>{clsBoundAppId}</Text>
                          </Text>
                        )}
                        <Text type="secondary">
                          {t("observability.clsEndpointPreview")}:{" "}
                          <Text code>{clsEndpointPreview}</Text>
                        </Text>
                      </Space>
                    }
                    rules={
                      clsAppMode === "existing"
                        ? [
                            {
                              required: true,
                              message: t("observability.clsTopicIdRequired"),
                            },
                          ]
                        : []
                    }
                  >
                    <Input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                  </Form.Item>

                  <Form.Item name="application_id" hidden>
                    <Input />
                  </Form.Item>

                  <Form.Item
                    name="use_internal_endpoint"
                    label={t("observability.clsInternalEndpoint")}
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    name="mask_content"
                    label={t("observability.clsMaskContent")}
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                </>
              )}

              <Space>
                <Button
                  type="primary"
                  loading={savingCls}
                  onClick={() => void handleSaveCls()}
                >
                  {t("common.save")}
                </Button>
                <Button
                  loading={testingCls}
                  disabled={!clsEnabled}
                  onClick={() => void handleTestCls()}
                >
                  {t("observability.testConnection")}
                </Button>
                <Button
                  icon={<RefreshCw size={14} />}
                  onClick={() => void fetchConfig()}
                >
                  {t("common.refresh")}
                </Button>
              </Space>
            </Form>
          ) : (
            <Form
              form={langfuseForm}
              layout="vertical"
              className={tabStyles.formFields}
            >
              <Form.Item
                name="enabled"
                label={t("observability.enable")}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>

              {langfuseEnabled && (
                <>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={t("observability.hint")}
                  />
                  <Form.Item
                    name="host"
                    label={t("observability.host")}
                    rules={[
                      {
                        required: true,
                        message: t("observability.hostRequired"),
                      },
                    ]}
                  >
                    <Input placeholder="https://cloud.langfuse.com" />
                  </Form.Item>
                  <Form.Item
                    name="public_key"
                    label={t("observability.publicKey")}
                    rules={[
                      {
                        required: true,
                        message: t("observability.publicKeyRequired"),
                      },
                    ]}
                  >
                    <Input placeholder="pk-lf-..." />
                  </Form.Item>
                  <Form.Item
                    name="secret_key"
                    label={t("observability.secretKey")}
                    extra={
                      langfuseSecretSet ? (
                        <Text type="secondary">
                          <CheckCircle2 size={12} style={{ marginRight: 4 }} />
                          {t("observability.secretKeySet")}
                        </Text>
                      ) : null
                    }
                    rules={
                      langfuseSecretSet
                        ? []
                        : [
                            {
                              required: true,
                              message: t("observability.secretKeyRequired"),
                            },
                          ]
                    }
                  >
                    <Input.Password placeholder="sk-lf-..." />
                  </Form.Item>
                </>
              )}

              <Space>
                <Button
                  type="primary"
                  loading={savingLangfuse}
                  onClick={() => void handleSaveLangfuse()}
                >
                  {t("common.save")}
                </Button>
                <Button
                  loading={testingLangfuse}
                  disabled={!langfuseEnabled}
                  onClick={() => void handleTestLangfuse()}
                >
                  {t("observability.testConnection")}
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
      )}
    </>
  );
}

export default ObservabilitySettingsPanel;
