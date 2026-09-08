import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Spin,
  Switch,
  Tag,
} from "antd";
import { Info, Settings2, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  pluginsApi,
  type AgentPlugin,
  type AgentPluginTool,
  type AgentPluginsConfig,
  type PluginConfigField,
} from "../../../../api/modules/plugins";
import { PluginIconView } from "../../../Admin/Plugins/PluginIconView";
import { message } from "../../../../utils/antdMessage";
import { apiErrorMessage } from "../../../../utils/apiError";
import pluginStyles from "../../../Admin/Plugins/index.module.less";
import styles from "./AgentPluginsPanel.module.less";

interface AgentPluginsPanelProps {
  agentId: string | null;
}

function toolsConfig(tools: AgentPluginTool[]): AgentPluginsConfig {
  const plugins: AgentPluginsConfig = {};
  for (const tool of tools) {
    const entry = (plugins[tool.plugin_id] ??= { tools: {} });
    entry.tools![tool.name] = {
      enabled: tool.enabled,
      config: { ...tool.config },
    };
  }
  return plugins;
}

function configField(field: PluginConfigField) {
  const props = {
    label: field.label || field.name,
    name: field.name,
    rules: field.required
      ? [{ required: true, message: field.label || field.name }]
      : undefined,
    extra: field.help,
  };
  if (field.type === "password") {
    return (
      <Form.Item key={field.name} {...props}>
        <Input.Password placeholder={field.placeholder} autoComplete="off" />
      </Form.Item>
    );
  }
  if (field.type === "number") {
    return (
      <Form.Item key={field.name} {...props}>
        <InputNumber
          style={{ width: "100%" }}
          placeholder={field.placeholder}
        />
      </Form.Item>
    );
  }
  return (
    <Form.Item key={field.name} {...props}>
      <Input placeholder={field.placeholder} />
    </Form.Item>
  );
}

export default function AgentPluginsPanel({ agentId }: AgentPluginsPanelProps) {
  const { t } = useTranslation();
  const [plugins, setPlugins] = useState<AgentPlugin[]>([]);
  const [tools, setTools] = useState<AgentPluginTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [configTool, setConfigTool] = useState<AgentPluginTool | null>(null);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!agentId) {
      setPlugins([]);
      setTools([]);
      return;
    }
    setLoading(true);
    try {
      const [pluginResult, toolResult] = await Promise.all([
        pluginsApi.listAgentPlugins(agentId),
        pluginsApi.listAgentTools(agentId),
      ]);
      setPlugins(pluginResult.plugins);
      setTools(toolResult.tools);
    } catch (error) {
      message.error(apiErrorMessage(error, t("plugins.loadError"), t));
    } finally {
      setLoading(false);
    }
  }, [agentId, t]);

  useEffect(() => {
    // Defer to a microtask so the initial setLoading(true) inside `load`
    // doesn't run synchronously within the effect body.
    queueMicrotask(() => {
      void load();
    });
  }, [load]);

  const detail = plugins.find((plugin) => plugin.id === detailId) ?? null;
  const detailTools = useMemo(
    () => tools.filter((tool) => tool.plugin_id === detailId),
    [detailId, tools],
  );

  const togglePlugin = async (plugin: AgentPlugin, enabled: boolean) => {
    if (!agentId || !plugin.global_enabled) return;
    setSaving(`plugin:${plugin.id}`);
    try {
      const result = await pluginsApi.patchAgentPlugins(agentId, {
        [plugin.id]: { enabled },
      });
      setPlugins(result.plugins);
      message.success(t("plugins.saved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("plugins.saveFailed"), t));
    } finally {
      setSaving(null);
    }
  };

  const persistTools = async (next: AgentPluginTool[]) => {
    if (!agentId) return;
    await pluginsApi.patchAgentTools(agentId, toolsConfig(next));
    setTools(next);
  };

  const toggleTool = async (tool: AgentPluginTool, enabled: boolean) => {
    const key = `tool:${tool.plugin_id}:${tool.name}`;
    setSaving(key);
    const next = tools.map((item) =>
      item.plugin_id === tool.plugin_id && item.name === tool.name
        ? { ...item, enabled }
        : item,
    );
    try {
      await persistTools(next);
      message.success(t("plugins.saved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("plugins.saveFailed"), t));
    } finally {
      setSaving(null);
    }
  };

  const openConfig = (tool: AgentPluginTool) => {
    setConfigTool(tool);
    form.setFieldsValue(tool.config);
  };

  const saveConfig = async () => {
    if (!configTool) return;
    const values = await form.validateFields();
    const key = `tool:${configTool.plugin_id}:${configTool.name}`;
    setSaving(key);
    try {
      await persistTools(
        tools.map((item) =>
          item.plugin_id === configTool.plugin_id &&
          item.name === configTool.name
            ? { ...item, config: values }
            : item,
        ),
      );
      setConfigTool(null);
      message.success(t("plugins.saved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("plugins.saveFailed"), t));
    } finally {
      setSaving(null);
    }
  };

  if (!agentId) {
    return (
      <Empty
        description={t("skills.noAgentSelected")}
        style={{ marginTop: 64 }}
      />
    );
  }
  if (loading) {
    return (
      <div className={styles.loading}>
        <Spin />
      </div>
    );
  }
  if (plugins.length === 0) {
    return <Empty description={t("plugins.noPlugins")} />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.hint}>
        <Info size={15} className={styles.hintIcon} />
        <span>{t("plugins.agentPluginHint")}</span>
      </div>
      <div className={pluginStyles.cardGrid}>
        {plugins.map((plugin) => (
          <article
            key={plugin.id}
            className={`${pluginStyles.card} ${
              plugin.enabled ? "" : pluginStyles.cardDisabled
            }`}
          >
            <div className={pluginStyles.cardBody}>
              <div className={pluginStyles.cardTop}>
                <PluginIconView
                  icon={plugin.icon}
                  size={48}
                  className={pluginStyles.cardIcon}
                />
                <div className={pluginStyles.cardTitleCol}>
                  <h3 className={pluginStyles.cardName}>
                    {plugin.name || plugin.id}
                  </h3>
                  <div className={pluginStyles.cardChips}>
                    {plugin.kind ? <Tag>{plugin.kind}</Tag> : null}
                    {!plugin.global_enabled ? (
                      <Tag>{t("plugins.globallyDisabled")}</Tag>
                    ) : null}
                  </div>
                </div>
              </div>
              <p className={pluginStyles.cardDesc}>
                {plugin.description || t("plugins.noDescription")}
              </p>
            </div>
            <div className={pluginStyles.cardFooter}>
              <button
                type="button"
                className={pluginStyles.detailLink}
                onClick={() => setDetailId(plugin.id)}
              >
                {t("plugins.viewDetails")}
              </button>
              <span className={pluginStyles.cardFooterSpacer} />
              <Switch
                size="small"
                checked={plugin.enabled}
                disabled={!plugin.global_enabled}
                loading={saving === `plugin:${plugin.id}`}
                onChange={(checked) => void togglePlugin(plugin, checked)}
              />
            </div>
          </article>
        ))}
      </div>

      <Drawer
        title={detail?.name || detail?.id}
        open={!!detail}
        onClose={() => setDetailId(null)}
        width={500}
        destroyOnHidden
      >
        {detail ? (
          <>
            {!detail.global_enabled ? (
              <Alert
                type="warning"
                showIcon
                message={t("plugins.globalDisabledHint")}
              />
            ) : null}
            <p className={styles.detailDescription}>
              {detail.description || t("plugins.noDescription")}
            </p>
            <div className={styles.pluginSwitch}>
              <span>{t("plugins.agentEnabled")}</span>
              <Switch
                checked={detail.enabled}
                disabled={!detail.global_enabled}
                loading={saving === `plugin:${detail.id}`}
                onChange={(checked) => void togglePlugin(detail, checked)}
              />
            </div>
            <h4>{t("plugins.colTools")}</h4>
            {detailTools.length === 0 ? (
              <Empty description={t("plugins.noToolsListed")} />
            ) : (
              <div className={pluginStyles.detailTools}>
                {detailTools.map((tool) => {
                  const key = `tool:${tool.plugin_id}:${tool.name}`;
                  const configurable = (tool.config_fields?.length ?? 0) > 0;
                  return (
                    <div key={key} className={pluginStyles.detailToolItem}>
                      <span className={pluginStyles.detailToolIcon} aria-hidden>
                        <Wrench size={15} />
                      </span>
                      <div className={pluginStyles.detailToolMeta}>
                        <div className={pluginStyles.detailToolName}>
                          {tool.name}
                        </div>
                        {tool.description ? (
                          <div className={pluginStyles.detailToolDesc}>
                            {tool.description}
                          </div>
                        ) : null}
                      </div>
                      <div className={pluginStyles.detailToolActions}>
                        {configurable ? (
                          <Button
                            type="text"
                            size="small"
                            icon={<Settings2 size={15} />}
                            disabled={!detail.enabled}
                            onClick={() => openConfig(tool)}
                            aria-label={t("plugins.configure")}
                          />
                        ) : null}
                        <Switch
                          size="small"
                          checked={tool.enabled}
                          disabled={!detail.enabled}
                          loading={saving === key}
                          onChange={(checked) => void toggleTool(tool, checked)}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        ) : null}
      </Drawer>

      <Drawer
        title={configTool?.name}
        open={!!configTool}
        onClose={() => setConfigTool(null)}
        width={420}
        destroyOnHidden
        extra={
          <Button
            type="primary"
            loading={saving?.startsWith("tool:")}
            onClick={() => void saveConfig()}
          >
            {t("common.save")}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          {configTool?.config_fields.map(configField)}
        </Form>
      </Drawer>
    </div>
  );
}
