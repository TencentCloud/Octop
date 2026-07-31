import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import { Package, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { pluginsApi, type InstalledPlugin } from "../../../api/modules/plugins";

const { Text, Paragraph } = Typography;

/** Server-wide plugin install / uninstall list. */
export function InstalledPluginsPanel() {
  const { t } = useTranslation();
  const [plugins, setPlugins] = useState<InstalledPlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [installOpen, setInstallOpen] = useState(false);
  const [installUrl, setInstallUrl] = useState("");
  const [installing, setInstalling] = useState(false);

  const fetchPlugins = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await pluginsApi.list();
      setPlugins(rows);
    } catch (err) {
      message.error(t("plugins.loadError"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchPlugins();
  }, [fetchPlugins]);

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
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("plugins.installFailed"),
      );
    } finally {
      setInstalling(false);
    }
  };

  const handleUninstall = async (pluginId: string) => {
    try {
      await pluginsApi.uninstall(pluginId);
      message.success(t("plugins.uninstallSuccess"));
      await fetchPlugins();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("plugins.uninstallFailed"),
      );
    }
  };

  const columns = [
    {
      title: t("plugins.colName"),
      key: "name",
      render: (_: unknown, row: InstalledPlugin) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.name || row.id}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.id}
            {row.version ? ` · v${row.version}` : ""}
          </Text>
        </Space>
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
      width: 120,
      render: (_: unknown, row: InstalledPlugin) => {
        if (row.error)
          return <Tag color="error">{t("plugins.statusError")}</Tag>;
        return (
          <Tag color={row.loaded ? "success" : "default"}>
            {row.loaded ? t("plugins.statusLoaded") : t("plugins.statusIdle")}
          </Tag>
        );
      },
    },
    {
      title: t("plugins.colTools"),
      key: "tools",
      render: (_: unknown, row: InstalledPlugin) => {
        const names = (row.tools || []).map((tool) => tool.name);
        if (!names.length) return <Text type="secondary">—</Text>;
        return (
          <Space size={[4, 4]} wrap>
            {names.map((name) => (
              <Tag key={name}>{name}</Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: "",
      key: "actions",
      width: 80,
      render: (_: unknown, row: InstalledPlugin) => (
        <Popconfirm
          title={t("plugins.uninstallConfirm", { id: row.id })}
          onConfirm={() => void handleUninstall(row.id)}
        >
          <Button
            type="text"
            danger
            icon={<Trash2 size={16} />}
            aria-label={t("plugins.uninstall")}
          />
        </Popconfirm>
      ),
    },
  ];

  return (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 16,
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <Paragraph type="secondary" style={{ margin: 0, maxWidth: 560 }}>
          {t("plugins.adminHint")}
        </Paragraph>
        <Button
          type="primary"
          icon={<Plus size={16} />}
          onClick={() => setInstallOpen(true)}
        >
          {t("plugins.install")}
        </Button>
      </div>
      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={plugins}
        pagination={false}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("plugins.empty")}
            />
          ),
        }}
      />

      <Modal
        title={t("plugins.installTitle")}
        open={installOpen}
        onCancel={() => setInstallOpen(false)}
        onOk={() => void handleInstall()}
        confirmLoading={installing}
        okText={t("plugins.install")}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <Text type="secondary">{t("plugins.installUrlHint")}</Text>
          <Input
            prefix={<Package size={16} />}
            placeholder="https://example.com/my-plugin.zip"
            value={installUrl}
            onChange={(e) => setInstallUrl(e.target.value)}
            onPressEnter={() => void handleInstall()}
          />
        </Space>
      </Modal>
    </>
  );
}
