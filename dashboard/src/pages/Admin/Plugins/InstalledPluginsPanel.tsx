import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import {
  Alert,
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Segmented,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  BookOpen,
  LayoutGrid,
  List,
  Package,
  Plus,
  Settings2,
  Trash2,
  Upload,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  pluginsApi,
  type AgentPluginTool,
  type AgentPluginsConfig,
  type InstalledPlugin,
  type PluginConfigField,
} from "../../../api/modules/plugins";
import { ResizableTable } from "../../../components/ResizableTable";
import { CardSkeleton } from "../../../components/Skeleton";
import { useAgent } from "../../../context/AgentContext";
import { useCardTableView } from "../../../hooks/useCardTableView";
import {
  ensureBuiltinToolRenderers,
  reloadPluginToolUis,
} from "../../../plugins/toolRenderers";
import { updateToolPluginIndex } from "../../../plugins/toolRenderers/toolPluginIndex";
import { apiErrorMessage } from "../../../utils/apiError";
import styles from "./index.module.less";
import { PluginIconView } from "./PluginIconView";

const { Text, Paragraph } = Typography;

async function syncPluginUis(rows: InstalledPlugin[]): Promise<void> {
  ensureBuiltinToolRenderers();
  updateToolPluginIndex(rows);
  await reloadPluginToolUis(rows);
}

function statusTag(row: InstalledPlugin, t: (key: string) => string) {
  if (row.error) return <Tag color="error">{t("plugins.statusError")}</Tag>;
  if (row.enabled === false)
    return <Tag color="default">{t("plugins.statusDisabled")}</Tag>;
  return (
    <Tag color={row.loaded ? "success" : "default"}>
      {row.loaded ? t("plugins.statusLoaded") : t("plugins.statusIdle")}
    </Tag>
  );
}

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

/** Server-wide plugin install / uninstall list (+ per-agent tools in detail). */
export function InstalledPluginsPanel() {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const [plugins, setPlugins] = useState<InstalledPlugin[]>([]);
  const [agentTools, setAgentTools] = useState<AgentPluginTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [installOpen, setInstallOpen] = useState(false);
  const [installUrl, setInstallUrl] = useState("");
  const [installing, setInstalling] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [toolSavingKey, setToolSavingKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<InstalledPlugin | null>(null);
  const [configTool, setConfigTool] = useState<AgentPluginTool | null>(null);
  const [form] = Form.useForm();
  const agentRef = useRef(activeAgentId);
  const { viewMode, setViewMode, showCardView } = useCardTableView("card");

  useEffect(() => {
    agentRef.current = activeAgentId;
  }, [activeAgentId]);

  const fetchPlugins = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await pluginsApi.list();
      setPlugins(rows);
      void syncPluginUis(rows).catch((err) =>
        console.warn("[plugin-ui] sync after list failed:", err),
      );
    } catch (err) {
      message.error(t("plugins.loadError"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [t]);

  const fetchAgentTools = useCallback(async () => {
    if (!activeAgentId) {
      setAgentTools([]);
      return;
    }
    const agentId = activeAgentId;
    try {
      const data = await pluginsApi.listAgentTools(agentId);
      if (agentRef.current === agentId) {
        setAgentTools(data.tools || []);
      }
    } catch (err) {
      console.error(err);
    }
  }, [activeAgentId]);

  useEffect(() => {
    void fetchPlugins();
  }, [fetchPlugins]);

  useEffect(() => {
    void fetchAgentTools();
  }, [fetchAgentTools]);

  const handleInstall = async () => {
    const url = installUrl.trim();
    if (!url) return;
    setInstalling(true);
    try {
      await pluginsApi.install(url);
      message.success(t("plugins.installSuccess"));
      setInstallOpen(false);
      setInstallUrl("");
      await fetchPlugins();
      await fetchAgentTools();
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.installFailed"), t));
    } finally {
      setInstalling(false);
    }
  };

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!next) return;
    if (!next.name.toLowerCase().endsWith(".zip")) {
      message.error(t("plugins.zipOnly"));
      return;
    }
    setUploading(true);
    try {
      await pluginsApi.upload(next, overwrite);
      message.success(t("plugins.installSuccess"));
      await fetchPlugins();
      await fetchAgentTools();
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.installFailed"), t));
    } finally {
      setUploading(false);
    }
  };

  const handleReload = async () => {
    setReloading(true);
    try {
      await pluginsApi.reload();
      message.success(t("plugins.reloadSuccess"));
      await fetchPlugins();
      await fetchAgentTools();
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.reloadFailed"), t));
    } finally {
      setReloading(false);
    }
  };

  const handleUninstall = async (pluginId: string) => {
    try {
      await pluginsApi.uninstall(pluginId);
      message.success(t("plugins.uninstallSuccess"));
      if (detail?.id === pluginId) setDetail(null);
      await fetchPlugins();
      await fetchAgentTools();
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.uninstallFailed"), t));
    }
  };

  const handleToggleEnabled = async (
    row: InstalledPlugin,
    enabled: boolean,
  ) => {
    setTogglingId(row.id);
    try {
      const updated = await pluginsApi.setEnabled(row.id, enabled);
      setPlugins((prev) =>
        prev.map((item) =>
          item.id === row.id ? { ...item, ...updated } : item,
        ),
      );
      setDetail((prev) =>
        prev?.id === row.id ? { ...prev, ...updated } : prev,
      );
      message.success(
        enabled ? t("plugins.enabledSuccess") : t("plugins.disabledSuccess"),
      );
      await fetchPlugins();
      await fetchAgentTools();
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.enableFailed"), t));
    } finally {
      setTogglingId(null);
    }
  };

  const toolKey = (tool: AgentPluginTool) => `${tool.plugin_id}:${tool.name}`;

  const persistTools = useCallback(async (nextTools: AgentPluginTool[]) => {
    const agentId = agentRef.current;
    if (!agentId) return;
    await pluginsApi.patchAgentTools(agentId, buildPluginsConfig(nextTools));
    if (agentRef.current === agentId) setAgentTools(nextTools);
  }, []);

  const handleToggleTool = async (tool: AgentPluginTool, enabled: boolean) => {
    const key = toolKey(tool);
    setToolSavingKey(key);
    const next = agentTools.map((row) =>
      row.plugin_id === tool.plugin_id && row.name === tool.name
        ? { ...row, enabled }
        : row,
    );
    try {
      await persistTools(next);
      message.success(t("plugins.saved"));
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.saveFailed"), t));
    } finally {
      setToolSavingKey(null);
    }
  };

  const openConfig = (tool: AgentPluginTool) => {
    setConfigTool(tool);
    form.setFieldsValue(tool.config || {});
  };

  const saveConfig = async () => {
    if (!configTool) return;
    const values = await form.validateFields();
    const next = agentTools.map((row) =>
      row.plugin_id === configTool.plugin_id && row.name === configTool.name
        ? { ...row, config: values, enabled: true }
        : row,
    );
    setToolSavingKey(toolKey(configTool));
    try {
      await persistTools(next);
      message.success(t("plugins.saved"));
      setConfigTool(null);
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.saveFailed"), t));
    } finally {
      setToolSavingKey(null);
    }
  };

  const detailTools =
    detail == null
      ? []
      : agentTools.filter((tool) => tool.plugin_id === detail.id);

  const columns = [
    {
      title: t("plugins.colName"),
      key: "name",
      width: 220,
      ellipsis: true,
      render: (_: unknown, row: InstalledPlugin) => (
        <span className={styles.tableNameCell}>
          <PluginIconView icon={row.icon} size={28} />
          <span className={styles.tableNameText}>{row.name || row.id}</span>
        </span>
      ),
    },
    {
      title: t("plugins.colId"),
      dataIndex: "id",
      key: "id",
      width: 160,
      ellipsis: true,
      render: (id: string) => <span className={styles.tableMono}>{id}</span>,
    },
    {
      title: t("plugins.colVersion"),
      dataIndex: "version",
      key: "version",
      width: 96,
      render: (version: string | undefined) => (
        <span className={styles.tableCellSingle}>{version || "—"}</span>
      ),
    },
    {
      title: t("plugins.colKind"),
      dataIndex: "kind",
      key: "kind",
      width: 100,
      render: (kind: string | undefined) => <Tag>{kind || "—"}</Tag>,
    },
    {
      title: t("plugins.colStatus"),
      key: "status",
      width: 110,
      render: (_: unknown, row: InstalledPlugin) => statusTag(row, t),
    },
    {
      title: t("plugins.colEnabled"),
      key: "enabled",
      width: 88,
      render: (_: unknown, row: InstalledPlugin) => (
        <Switch
          size="small"
          checked={row.enabled !== false}
          loading={togglingId === row.id}
          disabled={!!row.error}
          onChange={(checked) => void handleToggleEnabled(row, checked)}
        />
      ),
    },
    {
      title: t("plugins.colActions"),
      key: "actions",
      width: 128,
      render: (_: unknown, row: InstalledPlugin) => (
        <div className={styles.tableActions}>
          <Button type="link" size="small" onClick={() => setDetail(row)}>
            {t("plugins.viewDetails")}
          </Button>
          <Popconfirm
            title={t("plugins.uninstallConfirm", { id: row.id })}
            onConfirm={() => void handleUninstall(row.id)}
          >
            <Button
              type="text"
              danger
              size="small"
              className={styles.iconBtn}
              icon={<Trash2 size={15} />}
              aria-label={t("plugins.uninstall")}
            />
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.panel}>
      <Collapse
        className={styles.guide}
        items={[
          {
            key: "guide",
            label: (
              <span className={styles.guideLabel}>
                <BookOpen size={15} />
                {t("plugins.guideTitle")}
              </span>
            ),
            children: (
              <div className={styles.guideBody}>
                <div className={styles.guideSection}>
                  <Text strong>{t("plugins.guideDevelopTitle")}</Text>
                  <Paragraph className={styles.guideText}>
                    {t("plugins.guideDevelopBody")}
                  </Paragraph>
                </div>
                <div className={styles.guideSection}>
                  <Text strong>{t("plugins.guidePackageTitle")}</Text>
                  <Paragraph className={styles.guideText}>
                    {t("plugins.guidePackageBody")}
                  </Paragraph>
                </div>
                <div className={styles.guideSection}>
                  <Text strong>{t("plugins.guideImportTitle")}</Text>
                  <Paragraph className={styles.guideText}>
                    {t("plugins.guideImportBody")}
                  </Paragraph>
                </div>
                <div className={styles.guideSection}>
                  <Text strong>{t("plugins.guideExampleTitle")}</Text>
                  <pre className={styles.codeBlock}>
                    {t("plugins.guideExampleYaml")}
                  </pre>
                </div>
              </div>
            ),
          },
        ]}
      />

      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <span className={styles.toolbarCount}>
            {t("plugins.totalPlugins", { count: plugins.length })}
          </span>
        </div>
        <div className={styles.toolbarRight}>
          <Segmented
            size="small"
            value={viewMode}
            onChange={(v) => setViewMode(v as "card" | "table")}
            options={[
              {
                value: "card",
                label: (
                  <span className={styles.viewModeLabel}>
                    <LayoutGrid size={14} />
                    {t("plugins.viewCard")}
                  </span>
                ),
              },
              {
                value: "table",
                label: (
                  <span className={styles.viewModeLabel}>
                    <List size={14} />
                    {t("plugins.viewTable")}
                  </span>
                ),
              },
            ]}
          />
          <Checkbox
            checked={overwrite}
            onChange={(e) => setOverwrite(e.target.checked)}
          >
            {t("plugins.overwriteInstall")}
          </Checkbox>
          <Button loading={reloading} onClick={() => void handleReload()}>
            {t("plugins.reload")}
          </Button>
          <Button
            icon={<Upload size={16} />}
            loading={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            {t("plugins.installFromZip")}
          </Button>
          <Button
            type="primary"
            icon={<Plus size={16} />}
            onClick={() => setInstallOpen(true)}
          >
            {t("plugins.install")}
          </Button>
        </div>
      </div>

      {showCardView ? (
        loading ? (
          <CardSkeleton count={3} />
        ) : plugins.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t("plugins.empty")}
          />
        ) : (
          <div className={styles.cardGrid}>
            {plugins.map((row) => {
              const enabled = row.enabled !== false;
              return (
                <article
                  key={row.id}
                  className={`${styles.card} ${
                    enabled ? "" : styles.cardDisabled
                  }`}
                >
                  <div className={styles.cardBody}>
                    <div className={styles.cardTop}>
                      <PluginIconView
                        icon={row.icon}
                        size={48}
                        className={styles.cardIcon}
                      />
                      <div className={styles.cardTitleCol}>
                        <h3 className={styles.cardName}>
                          {row.name || row.id}
                        </h3>
                        <div className={styles.cardChips}>
                          {row.kind ? <Tag>{row.kind}</Tag> : null}
                          {statusTag(row, t)}
                        </div>
                      </div>
                    </div>
                    <p className={styles.cardDesc}>
                      {row.error ||
                        row.description ||
                        t("plugins.noDescription")}
                    </p>
                  </div>
                  <div className={styles.cardFooter}>
                    <button
                      type="button"
                      className={styles.detailLink}
                      onClick={() => setDetail(row)}
                    >
                      {t("plugins.viewDetails")}
                    </button>
                    <span className={styles.cardFooterSpacer} />
                    <Switch
                      size="small"
                      checked={enabled}
                      loading={togglingId === row.id}
                      disabled={!!row.error}
                      onChange={(checked) =>
                        void handleToggleEnabled(row, checked)
                      }
                    />
                    <Popconfirm
                      title={t("plugins.uninstallConfirm", { id: row.id })}
                      onConfirm={() => void handleUninstall(row.id)}
                    >
                      <Button
                        type="text"
                        danger
                        size="small"
                        className={styles.iconBtn}
                        icon={<Trash2 size={15} />}
                        aria-label={t("plugins.uninstall")}
                      />
                    </Popconfirm>
                  </div>
                </article>
              );
            })}
          </div>
        )
      ) : (
        <ResizableTable
          storageKey="admin-plugins"
          className={styles.table}
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={plugins}
          pagination={false}
          scroll={{ x: 960 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t("plugins.empty")}
              />
            ),
          }}
        />
      )}

      <Drawer
        title={
          detail ? (
            <div className={styles.drawerTitleBar}>
              <PluginIconView icon={detail.icon} size={40} />
              <div className={styles.drawerTitleMeta}>
                <div className={styles.drawerTitleText}>
                  {detail.name || detail.id}
                </div>
                <div className={styles.drawerTitleId}>{detail.id}</div>
              </div>
            </div>
          ) : (
            t("plugins.detailTitle")
          )
        }
        open={!!detail}
        onClose={() => setDetail(null)}
        width={500}
        destroyOnHidden
        styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
      >
        {detail ? (
          <div className={styles.drawerContent}>
            {detail.error ? (
              <Alert
                type="error"
                showIcon
                message={detail.error}
                className={styles.drawerAlert}
              />
            ) : null}

            <p className={styles.drawerDesc}>
              {detail.description || t("plugins.noDescription")}
            </p>

            <div className={styles.drawerChips}>
              {detail.kind ? <Tag>{detail.kind}</Tag> : null}
              {detail.version ? (
                <Tag>
                  {t("plugins.colVersion")} {detail.version}
                </Tag>
              ) : null}
              {statusTag(detail, t)}
              {detail.ui?.entry ? (
                <Tag color="blue">{t("plugins.hasUi")}</Tag>
              ) : null}
            </div>

            <div className={styles.drawerEnableRow}>
              <div className={styles.drawerEnableText}>
                <span className={styles.drawerEnableLabel}>
                  {t("plugins.colEnabled")}
                </span>
                <span className={styles.drawerEnableHint}>
                  {t("plugins.detailEnableHint")}
                </span>
              </div>
              <Switch
                checked={detail.enabled !== false}
                loading={togglingId === detail.id}
                disabled={!!detail.error}
                onChange={(checked) =>
                  void handleToggleEnabled(detail, checked)
                }
              />
            </div>

            <section className={styles.drawerSection}>
              <h4 className={styles.drawerSectionTitle}>
                {t("plugins.detailInfo")}
              </h4>
              <div className={styles.detailList}>
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>
                    {t("plugins.colPath")}
                  </span>
                  <span
                    className={`${styles.detailValue} ${styles.detailMono}`}
                  >
                    {detail.path || "—"}
                  </span>
                </div>
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>
                    {t("plugins.colUi")}
                  </span>
                  <span
                    className={`${styles.detailValue} ${styles.detailMono}`}
                  >
                    {detail.ui?.entry || "—"}
                  </span>
                </div>
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>
                    {t("plugins.colRequires")}
                  </span>
                  <span className={styles.detailValue}>
                    {(detail.requires || []).length > 0 ? (
                      <span className={styles.requiresTags}>
                        {detail.requires!.map((req) => (
                          <Tag key={req}>{req}</Tag>
                        ))}
                      </span>
                    ) : (
                      "—"
                    )}
                  </span>
                </div>
              </div>
            </section>

            <section className={styles.drawerSection}>
              <div className={styles.toolsSectionHead}>
                <h4 className={styles.drawerSectionTitle}>
                  {t("plugins.colTools")}
                </h4>
                {detailTools.length > 0 ? (
                  <span className={styles.toolsCountBadge}>
                    {detailTools.length}
                  </span>
                ) : null}
              </div>
              {!activeAgentId ? (
                <div className={styles.toolsEmpty}>{t("plugins.noAgent")}</div>
              ) : detail.enabled === false ? (
                <div className={styles.toolsEmpty}>
                  {t("plugins.enablePluginFirst")}
                </div>
              ) : detailTools.length === 0 ? (
                <div className={styles.toolsEmpty}>
                  {t("plugins.noToolsListed")}
                </div>
              ) : (
                <>
                  <p className={styles.toolsHint}>
                    {t("plugins.detailToolsHint")}
                  </p>
                  <div className={styles.detailTools}>
                    {detailTools.map((tool) => {
                      const key = toolKey(tool);
                      const busy = toolSavingKey === key;
                      const hasConfig = (tool.config_fields?.length ?? 0) > 0;
                      return (
                        <div
                          key={key}
                          className={`${styles.detailToolItem}${
                            tool.enabled ? "" : ` ${styles.detailToolItemOff}`
                          }`}
                        >
                          <span className={styles.detailToolIcon} aria-hidden>
                            <Wrench size={15} />
                          </span>
                          <div className={styles.detailToolMeta}>
                            <div className={styles.detailToolNameRow}>
                              <span className={styles.detailToolName}>
                                {tool.name}
                              </span>
                              {hasConfig ? (
                                <Tag className={styles.detailToolBadge}>
                                  {t("plugins.hasConfig")}
                                </Tag>
                              ) : null}
                            </div>
                            {tool.description ? (
                              <div className={styles.detailToolDesc}>
                                {tool.description}
                              </div>
                            ) : null}
                          </div>
                          <div className={styles.detailToolActions}>
                            {hasConfig ? (
                              <Button
                                type="text"
                                size="small"
                                className={styles.iconBtn}
                                icon={<Settings2 size={15} />}
                                onClick={() => openConfig(tool)}
                                disabled={busy}
                                aria-label={t("plugins.configure")}
                              />
                            ) : null}
                            <Switch
                              size="small"
                              checked={tool.enabled}
                              loading={busy}
                              onChange={(checked) =>
                                void handleToggleTool(tool, checked)
                              }
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </section>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        title={configTool ? configTool.name : ""}
        open={!!configTool}
        onClose={() => setConfigTool(null)}
        width={420}
        destroyOnHidden
        extra={
          <Button
            type="primary"
            onClick={() => void saveConfig()}
            loading={!!toolSavingKey}
          >
            {t("common.save")}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          {configTool?.config_fields?.map(renderConfigField)}
        </Form>
      </Drawer>

      <Modal
        title={t("plugins.installTitle")}
        open={installOpen}
        onCancel={() => setInstallOpen(false)}
        onOk={() => void handleInstall()}
        confirmLoading={installing}
        okText={t("plugins.install")}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <Alert type="info" showIcon message={t("plugins.installUrlHint")} />
          <Input
            prefix={<Package size={16} />}
            placeholder={t("plugins.installUrlPlaceholder")}
            value={installUrl}
            onChange={(e) => setInstallUrl(e.target.value)}
            onPressEnter={() => void handleInstall()}
          />
        </Space>
      </Modal>

      <input
        ref={fileInputRef}
        type="file"
        accept=".zip,application/zip"
        style={{ display: "none" }}
        onChange={(e) => void handleFileSelected(e)}
      />
    </div>
  );
}
