/**
 * Admin sandbox containers panel — embedded in the Admin Storage page.
 *
 * Ledger of local harness sandbox containers with image / network drift and
 * one-click recreate (backup → verify image → remove). See
 * docs/sandbox-image-management.md.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { App, Modal, Spin, Table, Tag, Typography } from "antd";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  sandboxAdminApi,
  type SandboxEntry,
  type SandboxImageRow,
} from "../../../api/modules/sandbox";
import { apiErrorMessage } from "../../../utils/apiError";
import { formatBytes } from "../../../utils/embeddingDownload";
import styles from "./storage.module.less";

function driftTag(
  value: boolean | null,
  t: (key: string) => string,
): React.ReactNode {
  if (value === null || value === undefined) {
    return <Tag>{t("adminSandbox.statusUnknown")}</Tag>;
  }
  if (value === false) {
    return <Tag color="green">{t("adminSandbox.statusOk")}</Tag>;
  }
  return <Tag color="orange">{t("adminSandbox.statusDrift")}</Tag>;
}

function networkCell(entry: SandboxEntry, t: (key: string) => string) {
  const offline = entry.network_offline;
  const label =
    offline === true
      ? t("adminSandbox.networkOffline")
      : offline === false
      ? t("adminSandbox.networkOnline")
      : t("adminSandbox.statusUnknown");
  const expected = entry.expected_allow_network;
  const expectLabel =
    expected === null || expected === undefined
      ? null
      : expected
      ? t("adminSandbox.networkOnline")
      : t("adminSandbox.networkOffline");
  return (
    <span>
      {label}
      {expectLabel !== null ? (
        <Typography.Text
          type="secondary"
          style={{ marginLeft: 6, fontSize: 12 }}
        >
          → {expectLabel}
        </Typography.Text>
      ) : null}
    </span>
  );
}

export function SandboxPanel() {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const [entries, setEntries] = useState<SandboxEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recreating, setRecreating] = useState<string | null>(null);
  const [imagesOpen, setImagesOpen] = useState(false);
  const [images, setImages] = useState<SandboxImageRow[]>([]);
  const [imagesLoading, setImagesLoading] = useState(false);

  const fetchEntries = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setEntries(await sandboxAdminApi.list());
    } catch (err) {
      setError(apiErrorMessage(err, t("adminSandbox.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchEntries();
  }, [fetchEntries]);

  const driftCount = useMemo(
    () => entries.filter((e) => e.drift || e.network_drift).length,
    [entries],
  );

  const handleRecreate = (entry: SandboxEntry) => {
    const affected =
      entry.affected_agents
        .map((a) => a.name || a.agent_id)
        .filter(Boolean)
        .join(", ") ||
      entry.agent_id ||
      "—";
    const turningOnline =
      entry.network_offline === true && entry.expected_allow_network === true;
    const turningOffline =
      entry.network_offline === false && entry.expected_allow_network === false;
    modal.confirm({
      title: t("adminSandbox.recreateTitle", { name: entry.container_name }),
      content: (
        <div>
          <p>{t("adminSandbox.recreateConfirm")}</p>
          <p>
            {t("adminSandbox.affectedAgents")}: {affected}
          </p>
          {turningOnline ? (
            <p style={{ color: "#d48806" }}>
              {t("adminSandbox.onlineWarning")}
            </p>
          ) : null}
          {turningOffline ? (
            <p style={{ color: "#d48806" }}>
              {t("adminSandbox.offlineWarning")}
            </p>
          ) : null}
        </div>
      ),
      okText: t("common.confirm"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        setRecreating(entry.container_name);
        try {
          const result = await sandboxAdminApi.recreate(entry.container_name);
          message.success(
            t("adminSandbox.recreateSuccess", {
              name: result.container_name,
              backup: result.backup_path,
            }),
          );
          await fetchEntries();
        } catch (err) {
          message.error(apiErrorMessage(err, t("adminSandbox.recreateFailed")));
        } finally {
          setRecreating(null);
        }
      },
    });
  };

  const openImages = async () => {
    setImagesOpen(true);
    setImagesLoading(true);
    try {
      setImages(await sandboxAdminApi.images());
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminSandbox.loadFailed")));
    } finally {
      setImagesLoading(false);
    }
  };

  const columns = [
    {
      title: t("adminSandbox.colContainer"),
      dataIndex: "container_name",
      key: "container_name",
      render: (v: string, entry: SandboxEntry) => (
        <span>
          {v}
          {entry.affected_agents.length > 0 ? (
            <Typography.Text
              type="secondary"
              style={{ display: "block", fontSize: 12 }}
            >
              {entry.affected_agents
                .map((a) => a.name || a.agent_id)
                .filter(Boolean)
                .join(", ")}
            </Typography.Text>
          ) : null}
        </span>
      ),
    },
    {
      title: t("adminSandbox.colScope"),
      dataIndex: "scope",
      key: "scope",
      width: 80,
    },
    {
      title: t("adminSandbox.colStatus"),
      dataIndex: "status",
      key: "status",
      width: 90,
    },
    {
      title: t("adminSandbox.colImage"),
      key: "image",
      render: (_: unknown, entry: SandboxEntry) => (
        <span>
          {entry.image}
          {entry.expected_image && entry.expected_image !== entry.image ? (
            <Typography.Text
              type="secondary"
              style={{ display: "block", fontSize: 12 }}
            >
              → {entry.expected_image}
            </Typography.Text>
          ) : null}
        </span>
      ),
    },
    {
      title: t("adminSandbox.colImageDrift"),
      key: "drift",
      width: 110,
      render: (_: unknown, entry: SandboxEntry) => driftTag(entry.drift, t),
    },
    {
      title: t("adminSandbox.colNetwork"),
      key: "network",
      render: (_: unknown, entry: SandboxEntry) => networkCell(entry, t),
    },
    {
      title: t("adminSandbox.colNetworkDrift"),
      key: "network_drift",
      width: 130,
      render: (_: unknown, entry: SandboxEntry) =>
        driftTag(entry.network_drift, t),
    },
    {
      title: t("adminSandbox.colActions"),
      key: "actions",
      width: 110,
      render: (_: unknown, entry: SandboxEntry) => (
        <button
          className={styles.toolbarBtn}
          disabled={recreating === entry.container_name}
          onClick={() => handleRecreate(entry)}
        >
          {recreating === entry.container_name
            ? t("adminSandbox.recreating")
            : t("adminSandbox.recreate")}
        </button>
      ),
    },
  ];

  return (
    <div className={styles.sandboxPanel}>
      <div className={styles.sandboxToolbar}>
        <span className={styles.gridCount}>
          {entries.length > 0
            ? t("adminSandbox.totalContainers", { count: entries.length })
            : ""}
          {driftCount > 0
            ? `${entries.length > 0 ? " · " : ""}${driftCount} ${t(
                "adminSandbox.driftSuffix",
              )}`
            : ""}
        </span>
        <span style={{ display: "flex", gap: 8 }}>
          <button
            className={styles.toolbarBtn}
            onClick={() => void openImages()}
          >
            {t("adminSandbox.viewImages")}
          </button>
          <button
            className={styles.toolbarBtn}
            onClick={() => void fetchEntries()}
            disabled={loading}
          >
            <RefreshCw
              size={12}
              style={{ marginRight: 4, verticalAlign: -2 }}
            />
            {t("common.refresh")}
          </button>
        </span>
      </div>
      {loading ? (
        <div className={styles.loadingState}>
          <Spin />
        </div>
      ) : error ? (
        <div className={styles.sandboxEmptyRow}>
          <span>{error}</span>
          <button
            className={styles.emptyAction}
            onClick={() => void fetchEntries()}
          >
            {t("common.retry")}
          </button>
        </div>
      ) : entries.length === 0 ? (
        <div className={styles.sandboxEmptyRow}>
          <span>{t("adminSandbox.empty")}</span>
        </div>
      ) : (
        <Table<SandboxEntry>
          rowKey="container_name"
          size="small"
          columns={columns}
          dataSource={entries}
          pagination={false}
          rowClassName={(entry) =>
            entry.drift || entry.network_drift ? styles.driftRow : ""
          }
        />
      )}

      <Modal
        title={t("adminSandbox.imagesTitle")}
        open={imagesOpen}
        onCancel={() => setImagesOpen(false)}
        footer={null}
        width={640}
      >
        <Table<SandboxImageRow>
          rowKey={(r) => r.id + (r.tag ?? "")}
          size="small"
          loading={imagesLoading}
          dataSource={images}
          pagination={false}
          columns={[
            {
              title: t("adminSandbox.colTag"),
              dataIndex: "tag",
              key: "tag",
              render: (v: string | null) => v ?? "<none>:<none>",
            },
            { title: "ID", dataIndex: "id", key: "id", width: 110 },
            {
              title: t("adminSandbox.colSize"),
              dataIndex: "size",
              key: "size",
              width: 100,
              render: (v: number) => formatBytes(v),
            },
            {
              title: t("adminSandbox.colReferenced"),
              dataIndex: "referenced",
              key: "referenced",
              width: 110,
              render: (v: boolean) => (v ? "✓" : ""),
            },
          ]}
        />
      </Modal>
    </div>
  );
}
