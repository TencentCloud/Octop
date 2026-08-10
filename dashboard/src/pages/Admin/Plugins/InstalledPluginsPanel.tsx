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

import { BookOpen, Package, Plus, Trash2, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { pluginsApi, type InstalledPlugin } from "../../../api/modules/plugins";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "../../Settings/AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

const { Text, Paragraph } = Typography;

/** Server-wide plugin install / uninstall list. */
export function InstalledPluginsPanel() {
  const { t } = useTranslation();
  const [plugins, setPlugins] = useState<InstalledPlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [installOpen, setInstallOpen] = useState(false);
  const [installUrl, setInstallUrl] = useState("");
  const [installing, setInstalling] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [overwrite, setOverwrite] = useState(false);

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
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.installFailed"), t));
    } finally {
      setUploading(false);
    }
  };

  const handleUninstall = async (pluginId: string) => {
    try {
      await pluginsApi.uninstall(pluginId);
      message.success(t("plugins.uninstallSuccess"));
      await fetchPlugins();
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.uninstallFailed"), t));
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
    <div className={styles.panel}>
      <TabPanelHeader
        icon={<Package size={22} />}
        title={t("plugins.tabInstalled")}
        description={t("plugins.adminHint")}
        actions={
          <Space size="small">
            <Checkbox
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
            >
              {t("plugins.overwriteInstall")}
            </Checkbox>
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
          </Space>
        }
      />

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
