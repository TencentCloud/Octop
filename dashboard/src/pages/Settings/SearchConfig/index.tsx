import { useEffect, useState, useCallback } from "react";
import {
  Button,
  Collapse,
  Form,
  Input,
  Tag,
  Typography,
  Spin,
  Alert,
  message,
  Divider,
  Modal,
} from "antd";
import {
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Search,
  Trash2,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { envsApi } from "../../../api/modules/env";
import api from "../../../api";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";

const { Text } = Typography;
const { Panel } = Collapse;

interface SearchProvider {
  id: string;
  name: string;
  descriptionKey: string;
  docs_url?: string;
  required_keys: string[];
  configured: boolean;
}

const SEARCH_PROVIDERS: SearchProvider[] = [
  {
    id: "tavily",
    name: "Tavily",
    descriptionKey: "setupWizard.search.providers.tavily.desc",
    docs_url: "https://app.tavily.com/",
    required_keys: ["TAVILY_API_KEY"],
    configured: false,
  },
  {
    id: "brave",
    name: "Brave Search",
    descriptionKey: "setupWizard.search.providers.brave.desc",
    docs_url: "https://api.search.brave.com/",
    required_keys: ["BRAVE_API_KEY"],
    configured: false,
  },
  {
    id: "google",
    name: "Google Search",
    descriptionKey: "setupWizard.search.providers.google.desc",
    docs_url: "https://programmablesearchengine.google.com/",
    required_keys: ["GOOGLE_API_KEY", "GOOGLE_CSE_ID"],
    configured: false,
  },
  {
    id: "kimi",
    name: "Kimi (Moonshot)",
    descriptionKey: "setupWizard.search.providers.kimi.desc",
    docs_url: "https://platform.moonshot.cn/",
    required_keys: ["MOONSHOT_API_KEY"],
    configured: false,
  },
];

interface ProviderPanelProps {
  provider: SearchProvider;
  envVars: Record<string, string>;
  onSaved: () => void;
}

function ProviderPanel({ provider, envVars, onSaved }: ProviderPanelProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    const initialValues: Record<string, string> = {};
    provider.required_keys.forEach((key) => {
      if (envVars[key]) initialValues[key] = envVars[key];
    });
    form.setFieldsValue(initialValues);
  }, [envVars, provider.required_keys, form]);

  const handleSave = async () => {
    try {
      setSaving(true);
      const values = (await form.validateFields()) as Record<string, string>;
      const allEnvs = { ...envVars };
      provider.required_keys.forEach((key) => {
        if (values[key]) allEnvs[key] = values[key];
      });
      await envsApi.batchSaveEnvs(allEnvs);
      message.success(
        t("setupWizard.search.saveSuccess", { name: provider.name }),
      );
      onSaved();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("setupWizard.search.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    try {
      setTesting(true);
      const values = (await form.validateFields()) as Record<string, string>;
      const testEnvs = { ...envVars };
      provider.required_keys.forEach((key) => {
        if (values[key]) testEnvs[key] = values[key];
      });
      const result = await api.testSearch(provider.id, testEnvs);
      if (result.success) {
        message.success(
          t("setupWizard.search.testSuccess", { name: provider.name }),
        );
      } else {
        message.error(
          t("setupWizard.search.testFailed", {
            name: provider.name,
            error: result.error || result.error_type || "Unknown error",
          }),
        );
      }
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        t("setupWizard.search.testFailed", {
          name: provider.name,
          error: err instanceof Error ? err.message : String(err),
        }),
      );
    } finally {
      setTesting(false);
    }
  };

  const handleRevoke = () => {
    Modal.confirm({
      title: t("setupWizard.search.revokeTitle", { name: provider.name }),
      content: t("setupWizard.search.revokeConfirm", { name: provider.name }),
      okText: t("setupWizard.search.revoke"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          setRevoking(true);
          // Delete all required env vars for this provider
          for (const key of provider.required_keys) {
            await envsApi.deleteEnv(key);
          }
          message.success(
            t("setupWizard.search.revokeSuccess", { name: provider.name }),
          );
          onSaved();
        } catch (err) {
          message.error(
            err instanceof Error
              ? err.message
              : t("setupWizard.search.revokeFailed"),
          );
        } finally {
          setRevoking(false);
        }
      },
    });
  };

  return (
    <div>
      <Form form={form} layout="vertical" size="small">
        {provider.required_keys.map((key) => (
          <Form.Item
            key={key}
            name={key}
            label={key}
            rules={[
              {
                required: true,
                message: t("setupWizard.search.required", { key }),
              },
            ]}
            extra={
              key === "GOOGLE_CSE_ID" ? (
                <span>
                  {t("setupWizard.search.googleCseIdHint")}
                  {provider.docs_url && (
                    <>
                      {" · "}
                      <a
                        href={provider.docs_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 12 }}
                      >
                        {t("setupWizard.search.getApiKey")}
                      </a>
                    </>
                  )}
                </span>
              ) : undefined
            }
          >
            <Input.Password placeholder={`Enter ${key}`} />
          </Form.Item>
        ))}
      </Form>

      <Divider style={{ margin: "12px 0 8px" }} />

      <div style={{ display: "flex", gap: 8 }}>
        <Button
          type="primary"
          size="small"
          loading={saving}
          onClick={handleSave}
        >
          {t("common.save")}
        </Button>
        <Button
          size="small"
          icon={<Zap size={14} />}
          loading={testing}
          onClick={handleTest}
        >
          {t("setupWizard.search.test")}
        </Button>
        {provider.docs_url && (
          <Button
            size="small"
            type="link"
            onClick={() => window.open(provider.docs_url, "_blank")}
          >
            {t("setupWizard.search.docs")}
          </Button>
        )}
        {provider.configured && (
          <Button
            size="small"
            danger
            icon={<Trash2 size={14} />}
            loading={revoking}
            onClick={handleRevoke}
          >
            {t("setupWizard.search.revoke")}
          </Button>
        )}
      </div>
    </div>
  );
}

export default function SearchConfigPage() {
  const { t } = useTranslation();
  const [providers, setProviders] =
    useState<SearchProvider[]>(SEARCH_PROVIDERS);
  const [loading, setLoading] = useState(true);
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [activeCollapseKey, setActiveCollapseKey] = useState<
    string | undefined
  >();

  const fetchEnvVars = useCallback(async () => {
    try {
      setLoading(true);
      const envs = await envsApi.listEnvs();
      const envMap: Record<string, string> = {};
      envs.forEach((env) => {
        envMap[env.key] = env.value;
      });
      setEnvVars(envMap);
      setProviders(
        SEARCH_PROVIDERS.map((p) => ({
          ...p,
          configured: p.required_keys.every((key) => !!envMap[key]),
        })),
      );
    } catch (err) {
      console.error("Failed to load env vars:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEnvVars();
  }, [fetchEnvVars]);

  const sortedProviders = [...providers].sort((a, b) => {
    if (a.configured && !b.configured) return -1;
    if (!a.configured && b.configured) return 1;
    return 0;
  });

  if (loading) {
    return (
      <div
        style={{ display: "flex", justifyContent: "center", padding: "40px 0" }}
      >
        <Spin />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <TabPanelHeader
        icon={<Search size={22} />}
        title={t("nav.search")}
        description={t("advancedSettings.search.desc")}
      />

      <Alert
        type="info"
        showIcon
        message={t("advancedSettings.search.tip")}
        style={{ fontSize: 13 }}
      />

      <Collapse
        accordion
        activeKey={activeCollapseKey}
        onChange={(key) =>
          setActiveCollapseKey(Array.isArray(key) ? key[0] : key)
        }
        expandIcon={({ isActive }) =>
          isActive ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        }
        style={{ background: "transparent" }}
      >
        {sortedProviders.map((provider) => (
          <Panel
            key={provider.id}
            header={
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  flex: 1,
                }}
              >
                <Search size={18} style={{ flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 500 }}>{provider.name}</span>
                  <Text
                    type="secondary"
                    style={{ fontSize: 12, display: "block", marginTop: 2 }}
                  >
                    {t(provider.descriptionKey)}
                  </Text>
                </div>
                {provider.configured ? (
                  <Tag
                    icon={<CheckCircle size={14} />}
                    color="success"
                    style={{ marginRight: 8 }}
                  >
                    {t("setupWizard.search.configured")}
                  </Tag>
                ) : (
                  <Tag
                    icon={<AlertCircle size={14} />}
                    color="default"
                    style={{ marginRight: 8 }}
                  >
                    {t("setupWizard.search.unconfigured")}
                  </Tag>
                )}
              </div>
            }
          >
            <ProviderPanel
              provider={provider}
              envVars={envVars}
              onSaved={fetchEnvVars}
            />
          </Panel>
        ))}
      </Collapse>

      <Text type="secondary" style={{ fontSize: 12 }}>
        {t("setupWizard.search.configuredCount", {
          count: providers.filter((p) => p.configured).length,
          total: providers.length,
        })}
      </Text>
    </div>
  );
}
