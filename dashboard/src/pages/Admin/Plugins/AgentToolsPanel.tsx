import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Switch,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import { Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CardSkeleton } from "../../../components/Skeleton";
import {
  pluginsApi,
  type AgentPluginTool,
  type AgentPluginsConfig,
  type PluginConfigField,
} from "../../../api/modules/plugins";
import { useAgent } from "../../../context/AgentContext";
import styles from "./index.module.less";

const { Text, Paragraph } = Typography;

function buildPluginsConfig(tools: AgentPluginTool[]): AgentPluginsConfig {
  const out: AgentPluginsConfig = {};
  for (const tool of tools) {
    if (!out[tool.plugin_id]) out[tool.plugin_id] = { tools: {} };
    out[tool.plugin_id].tools![tool.name] = {
      enabled: tool.enabled,
      config: { ...tool.config },
    };
  }
  return out;
}

function renderConfigField(field: PluginConfigField) {
  const common = {
    label: field.label || field.name,
    name: field.name,
    rules: field.required
      ? [{ required: true, message: field.label || field.name }]
      : undefined,
    extra: field.help,
  };
  if (field.type === "password") {
    return (
      <Form.Item key={field.name} {...common}>
        <Input.Password placeholder={field.placeholder} autoComplete="off" />
      </Form.Item>
    );
  }
  if (field.type === "number") {
    return (
      <Form.Item key={field.name} {...common}>
        <InputNumber
          style={{ width: "100%" }}
          placeholder={field.placeholder}
        />
      </Form.Item>
    );
  }
  return (
    <Form.Item key={field.name} {...common}>
      <Input placeholder={field.placeholder} />
    </Form.Item>
  );
}

/** Per-agent plugin tool enablement and configuration. */
export function AgentToolsPanel() {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const [tools, setTools] = useState<AgentPluginTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [configTool, setConfigTool] = useState<AgentPluginTool | null>(null);
  const [form] = Form.useForm();
  const agentRef = useRef(activeAgentId);

  useEffect(() => {
    agentRef.current = activeAgentId;
  }, [activeAgentId]);

  const fetchTools = useCallback(async () => {
    if (!activeAgentId) {
      setTools([]);
      setLoading(false);
      return;
    }
    const agentId = activeAgentId;
    setLoading(true);
    try {
      const data = await pluginsApi.listAgentTools(agentId);
      if (agentRef.current === agentId) {
        setTools(data.tools || []);
      }
    } catch (err) {
      message.error(t("plugins.loadError"));
      console.error(err);
    } finally {
      if (agentRef.current === agentId) setLoading(false);
    }
  }, [activeAgentId, t]);

  useEffect(() => {
    void fetchTools();
  }, [fetchTools]);

  const persist = useCallback(async (nextTools: AgentPluginTool[]) => {
    const agentId = agentRef.current;
    if (!agentId) return;
    await pluginsApi.patchAgentTools(agentId, buildPluginsConfig(nextTools));
    if (agentRef.current === agentId) setTools(nextTools);
  }, []);

  const toolKey = (tool: AgentPluginTool) => `${tool.plugin_id}:${tool.name}`;

  const handleToggle = async (tool: AgentPluginTool, enabled: boolean) => {
    const key = toolKey(tool);
    setSavingKey(key);
    const next = tools.map((row) =>
      row.plugin_id === tool.plugin_id && row.name === tool.name
        ? { ...row, enabled }
        : row,
    );
    try {
      await persist(next);
      message.success(t("plugins.saved"));
    } catch {
      message.error(t("plugins.saveFailed"));
    } finally {
      setSavingKey(null);
    }
  };

  const openConfig = (tool: AgentPluginTool) => {
    setConfigTool(tool);
    form.setFieldsValue(tool.config || {});
  };

  const saveConfig = async () => {
    if (!configTool) return;
    const values = await form.validateFields();
    const next = tools.map((row) =>
      row.plugin_id === configTool.plugin_id && row.name === configTool.name
        ? { ...row, config: values, enabled: true }
        : row,
    );
    setSavingKey(toolKey(configTool));
    try {
      await persist(next);
      message.success(t("plugins.saved"));
      setConfigTool(null);
    } catch {
      message.error(t("plugins.saveFailed"));
    } finally {
      setSavingKey(null);
    }
  };

  const grouped = useMemo(() => {
    const map = new Map<string, AgentPluginTool[]>();
    for (const tool of tools) {
      const list = map.get(tool.plugin_id) || [];
      list.push(tool);
      map.set(tool.plugin_id, list);
    }
    return [...map.entries()];
  }, [tools]);

  return (
    <>
      <Paragraph className={styles.hint}>{t("plugins.agentHint")}</Paragraph>

      {loading ? (
        <CardSkeleton count={3} />
      ) : !activeAgentId ? (
        <Empty description={t("plugins.noAgent")} />
      ) : tools.length === 0 ? (
        <Empty description={t("plugins.noTools")} />
      ) : (
        <div className={styles.list}>
          {grouped.map(([pluginId, pluginTools]) => (
            <Card
              key={pluginId}
              title={pluginId}
              size="small"
              className={styles.card}
            >
              {pluginTools.map((tool) => {
                const key = toolKey(tool);
                const busy = savingKey === key;
                return (
                  <div key={key} className={styles.row}>
                    <div className={styles.meta}>
                      <Text strong>{tool.name}</Text>
                      {tool.description ? (
                        <Text type="secondary" className={styles.desc}>
                          {tool.description}
                        </Text>
                      ) : null}
                    </div>
                    <div className={styles.actions}>
                      {(tool.config_fields?.length ?? 0) > 0 ? (
                        <Button
                          icon={<Settings2 size={16} />}
                          onClick={() => openConfig(tool)}
                          disabled={busy}
                        >
                          {t("plugins.configure")}
                        </Button>
                      ) : null}
                      <Switch
                        checked={tool.enabled}
                        loading={busy}
                        onChange={(checked) => void handleToggle(tool, checked)}
                      />
                    </div>
                  </div>
                );
              })}
            </Card>
          ))}
        </div>
      )}

      <Drawer
        title={configTool ? `${configTool.name}` : ""}
        open={!!configTool}
        onClose={() => setConfigTool(null)}
        width={420}
        destroyOnHidden
        extra={
          <Button
            type="primary"
            onClick={() => void saveConfig()}
            loading={!!savingKey}
          >
            {t("common.save")}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          {configTool?.config_fields?.map(renderConfigField)}
        </Form>
      </Drawer>
    </>
  );
}
