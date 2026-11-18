import { useCallback, useEffect, useState } from "react";
import {
  App,
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Spin,
  Switch,
  Tag,
} from "antd";
import { Cloud, Pencil, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  backupApi,
  type RemoteBackupObject,
  type RemoteBackupSummary,
  type RemoteMirrorStatus,
  type RemoteWebDavConfig,
} from "../../../api/modules/backup";
import { apiErrorMessage } from "../../../utils/apiError";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

function statusColor(
  status: RemoteMirrorStatus | undefined,
): "success" | "warning" | "error" | "default" {
  if (status === "remote_ok") return "success";
  if (status === "unverified") return "warning";
  if (status === "remote_failed") return "error";
  return "default";
}

export function MirrorStatusTag({
  status,
  emptyKey = "backup.remoteStatusLocalOnly",
}: {
  status: RemoteMirrorStatus | undefined;
  /** i18n key when status is missing (local list vs remote-only list). */
  emptyKey?: string;
}) {
  const { t } = useTranslation();
  if (!status) {
    return <Tag>{t(emptyKey)}</Tag>;
  }
  return (
    <Tag color={statusColor(status)}>
      {t(`backup.remoteStatus.${status}`, { defaultValue: status })}
    </Tag>
  );
}

function formatRemoteSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

interface RemoteBackupSectionProps {
  summary: RemoteBackupSummary | null;
  busy: boolean;
  timeZone: string;
  onChanged: () => void | Promise<void>;
  onToggleEnabled: (next: boolean) => void | Promise<void>;
  togglingEnabled: boolean;
}

export function RemoteBackupSection({
  summary,
  busy,
  timeZone,
  onChanged,
  onToggleEnabled,
  togglingEnabled,
}: RemoteBackupSectionProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [editOpen, setEditOpen] = useState(false);
  const [remoteListOpen, setRemoteListOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [remoteItems, setRemoteItems] = useState<RemoteBackupObject[]>([]);
  const [remoteLoading, setRemoteLoading] = useState(false);
  const [pulling, setPulling] = useState<string | null>(null);
  const [form] = Form.useForm<RemoteWebDavConfig>();

  const configured = Boolean(summary?.remote_backend_id && summary.endpoint);
  const enabled = Boolean(summary?.remote_enabled);

  const openEdit = () => {
    form.setFieldsValue({
      url: summary?.endpoint ?? "",
      username: summary?.username ?? "",
      password: undefined,
      base_dir: summary?.base_dir ?? "",
      verify_ssl: summary?.verify_ssl !== false,
      allow_insecure: Boolean(summary?.allow_insecure),
    });
    setEditOpen(true);
  };

  const onTest = async () => {
    setTesting(true);
    try {
      const values = await form.validateFields();
      const passwordEntered =
        typeof values.password === "string" && values.password.length > 0;
      // Blank password reuses the linked secret only for the same endpoint.
      await backupApi.testRemote({
        url: values.url.trim(),
        username: values.username?.trim() ?? "",
        password: passwordEntered ? values.password : null,
        base_dir: values.base_dir?.trim() ?? "",
        verify_ssl: values.verify_ssl !== false,
        allow_insecure: Boolean(values.allow_insecure),
      });
      message.success(t("backup.remoteTestOk"));
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(apiErrorMessage(err, t("backup.remoteTestFailed"), t));
    } finally {
      setTesting(false);
    }
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      const passwordEntered =
        typeof values.password === "string" && values.password.length > 0;
      await backupApi.saveRemoteWebDav({
        url: values.url.trim(),
        username: values.username?.trim() ?? "",
        // null keeps the stored secret on the server.
        password: passwordEntered ? values.password : null,
        base_dir: values.base_dir?.trim() ?? "",
        verify_ssl: values.verify_ssl !== false,
        allow_insecure: Boolean(values.allow_insecure),
      });
      message.success(t("backup.remoteSaveOk"));
      setEditOpen(false);
      await onChanged();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(apiErrorMessage(err, t("backup.remoteSaveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const loadRemoteList = useCallback(async () => {
    setRemoteLoading(true);
    try {
      const data = await backupApi.listRemote();
      setRemoteItems(data.items);
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.remoteListFailed"), t));
    } finally {
      setRemoteLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    if (remoteListOpen) void loadRemoteList();
  }, [remoteListOpen, loadRemoteList]);

  const onPull = async (name: string) => {
    setPulling(name);
    try {
      await backupApi.pullRemote(name);
      message.success(t("backup.remotePullOk", { name }));
      await onChanged();
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.remotePullFailed"), t));
    } finally {
      setPulling(null);
    }
  };

  const handleEnable = async (next: boolean) => {
    if (next && !summary?.remote_backend_id) {
      message.warning(t("backup.remoteEnableNeedsTarget"));
      openEdit();
      return;
    }
    await onToggleEnabled(next);
  };

  const last = summary?.last_mirror;

  return (
    <>
      <TabPanelHeader
        icon={<Cloud size={22} />}
        title={t("backup.remoteTitle")}
        description={t("backup.remoteDesc")}
      />
      <section className={styles.section}>
        <div className={styles.remoteCard}>
          <div className={styles.remoteCardMain}>
            <div className={styles.remoteProvider}>
              {configured ? (
                <>
                  <span className={styles.remoteKind}>
                    {(summary?.kind ?? "webdav").toUpperCase()}
                  </span>
                  <code className={styles.remoteEndpoint}>
                    {summary?.endpoint}
                    {summary?.base_dir ? ` ${summary.base_dir}` : ""}
                  </code>
                </>
              ) : (
                <span className={styles.remoteHint}>
                  {t("backup.remoteNotConfigured")}
                </span>
              )}
            </div>
            <div className={styles.remoteMeta}>
              <label className={styles.remoteEnableRow}>
                <span>{t("backup.remoteEnable")}</span>
                <Switch
                  checked={enabled}
                  disabled={busy || togglingEnabled}
                  loading={togglingEnabled}
                  onChange={(next) => void handleEnable(next)}
                />
              </label>
              {last ? (
                <span>
                  {t("backup.remoteLastMirror")}:{" "}
                  <MirrorStatusTag status={last.status} />{" "}
                  {formatServerIsoDateTime(last.checked_at, timeZone)}
                </span>
              ) : null}
            </div>
          </div>
          <div className={styles.remoteActions}>
            <Button
              icon={<Pencil size={14} />}
              disabled={busy}
              onClick={openEdit}
            >
              {t("backup.remoteEdit")}
            </Button>
            <Button
              disabled={busy || !configured}
              onClick={() => setRemoteListOpen(true)}
            >
              {t("backup.remoteListButton")}
            </Button>
          </div>
        </div>
      </section>

      <Modal
        title={t("backup.remoteEditTitle")}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        destroyOnHidden
        footer={[
          <Button key="test" loading={testing} onClick={() => void onTest()}>
            {t("backup.remoteTest")}
          </Button>,
          <Button key="cancel" onClick={() => setEditOpen(false)}>
            {t("common.cancel")}
          </Button>,
          <Button
            key="save"
            type="primary"
            loading={saving}
            onClick={() => void onSave()}
          >
            {t("common.save")}
          </Button>,
        ]}
      >
        <Form form={form} layout="vertical" requiredMark={false}>
          <Form.Item
            name="url"
            label={t("backup.remoteUrl")}
            rules={[{ required: true, message: t("backup.remoteUrlRequired") }]}
          >
            <Input placeholder="https://dav.example/remote.php/dav/files/user/" />
          </Form.Item>
          <Form.Item name="username" label={t("backup.remoteUsername")}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            label={t("backup.remotePassword")}
            extra={
              summary?.has_password
                ? t("backup.remotePasswordHint")
                : undefined
            }
          >
            <Input.Password
              autoComplete="new-password"
              placeholder={
                summary?.has_password
                  ? t("backup.remotePasswordKeep")
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item name="base_dir" label={t("backup.remoteBaseDir")}>
            <Input placeholder="octop-backups" />
          </Form.Item>
          <Form.Item
            name="verify_ssl"
            valuePropName="checked"
            initialValue={true}
          >
            <Checkbox>{t("backup.remoteVerifySsl")}</Checkbox>
          </Form.Item>
          <Form.Item name="allow_insecure" valuePropName="checked">
            <Checkbox>{t("backup.remoteAllowInsecure")}</Checkbox>
          </Form.Item>
          <p className={styles.autoHint}>{t("backup.remoteSaveHint")}</p>
        </Form>
      </Modal>

      <Modal
        title={t("backup.remoteListTitle")}
        open={remoteListOpen}
        onCancel={() => setRemoteListOpen(false)}
        footer={
          <Button
            icon={<RefreshCw size={14} />}
            onClick={() => void loadRemoteList()}
          >
            {t("common.refresh")}
          </Button>
        }
        width={640}
      >
        <Spin spinning={remoteLoading}>
          {!remoteLoading && remoteItems.length === 0 ? (
            <p className={styles.autoHint}>{t("backup.remoteListEmpty")}</p>
          ) : (
            <ul className={styles.remoteList}>
              {remoteItems.map((item) => (
                <li key={item.name} className={styles.remoteListItem}>
                  <div>
                    <div className={styles.backupCardName}>{item.name}</div>
                    <div className={styles.backupCardMeta}>
                      <span>{formatRemoteSize(item.size)}</span>
                      {item.modified_at ? (
                        <span>
                          {formatServerIsoDateTime(item.modified_at, timeZone)}
                        </span>
                      ) : null}
                      <MirrorStatusTag
                        status={item.remote_status}
                        emptyKey="backup.remoteStatusNotMirrored"
                      />
                    </div>
                  </div>
                  <Button
                    size="small"
                    loading={pulling === item.name}
                    disabled={busy}
                    onClick={() => void onPull(item.name)}
                  >
                    {t("backup.remotePull")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Spin>
      </Modal>
    </>
  );
}
