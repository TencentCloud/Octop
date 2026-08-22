import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { Copy, Link2, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  invitesApi,
  localInviteUrl,
  type InviteRow,
  type InviteStatus,
} from "../../../api/modules/invites";
import { message } from "@/utils/antdMessage";
import { apiErrorMessage } from "../../../utils/apiError";
import { copyText } from "../../../utils/copyText";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./index.module.less";

const { Text } = Typography;

const STATUS_COLOR: Record<InviteStatus, string> = {
  pending: "processing",
  used: "success",
  expired: "default",
  revoked: "warning",
};

interface InviteDrawerProps {
  open: boolean;
  onClose: () => void;
}

export default function InviteDrawer({ open, onClose }: InviteDrawerProps) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [rows, setRows] = useState<InviteRow[]>([]);
  const [form] = Form.useForm<{ note?: string; expires_in_days: number }>();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await invitesApi.list());
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminUsers.inviteLoadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({ expires_in_days: 7, note: undefined });
    void refresh();
  }, [open, form, refresh]);

  const onCreate = async (values: {
    note?: string;
    expires_in_days: number;
  }) => {
    setCreating(true);
    try {
      const row = await invitesApi.create({
        note: values.note?.trim() || null,
        expires_in_days: values.expires_in_days,
      });
      message.success(t("adminUsers.inviteCreateSuccess"));
      form.setFieldsValue({ note: undefined, expires_in_days: 7 });
      setRows((prev) => [row, ...prev.filter((r) => r.id !== row.id)]);
      const url = localInviteUrl(row.code);
      const ok = await copyText(url);
      if (ok) {
        message.success(t("adminUsers.inviteCopied"));
      }
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("adminUsers.inviteCreateFailed"), t),
      );
    } finally {
      setCreating(false);
    }
  };

  const onCopy = async (row: InviteRow) => {
    const url = localInviteUrl(row.code);
    const ok = await copyText(url);
    if (ok) message.success(t("adminUsers.inviteCopied"));
    else message.error(t("adminUsers.inviteCopyFailed"));
  };

  const onRevoke = async (row: InviteRow) => {
    try {
      const updated = await invitesApi.revoke(row.id);
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      message.success(t("adminUsers.inviteRevokeSuccess"));
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("adminUsers.inviteRevokeFailed"), t),
      );
    }
  };

  return (
    <Drawer
      title={t("adminUsers.inviteDrawerTitle")}
      placement="right"
      open={open}
      onClose={onClose}
      width={Math.min(
        560,
        typeof window !== "undefined" ? window.innerWidth - 24 : 560,
      )}
      destroyOnHidden
      className={styles.inviteDrawer}
      styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(v) => void onCreate(v)}
        initialValues={{ expires_in_days: 7 }}
        className={styles.inviteCreateForm}
      >
        <Form.Item
          name="note"
          label={t("adminUsers.inviteNote")}
          extra={t("adminUsers.inviteNoteHint")}
        >
          <Input
            maxLength={200}
            placeholder={t("adminUsers.inviteNotePlaceholder")}
            allowClear
          />
        </Form.Item>
        <Form.Item
          name="expires_in_days"
          label={t("adminUsers.inviteExpiresDays")}
          rules={[
            {
              required: true,
              message: t("adminUsers.inviteExpiresDaysRequired"),
            },
          ]}
        >
          <InputNumber min={1} max={90} style={{ width: "100%" }} />
        </Form.Item>
        <Button
          type="primary"
          htmlType="submit"
          icon={<Plus size={14} />}
          loading={creating}
          block
        >
          {t("adminUsers.inviteCreate")}
        </Button>
      </Form>

      <div className={styles.inviteListHeader}>
        <Text strong>{t("adminUsers.inviteListTitle")}</Text>
        <Button type="link" size="small" onClick={() => void refresh()}>
          {t("common.refresh")}
        </Button>
      </div>

      {loading ? (
        <div className={styles.inviteLoading}>
          <Spin />
        </div>
      ) : rows.length === 0 ? (
        <Empty description={t("adminUsers.inviteEmpty")} />
      ) : (
        <div className={styles.inviteList}>
          {rows.map((row) => (
            <div key={row.id} className={styles.inviteCard}>
              <div className={styles.inviteCardTop}>
                <Space size={8} wrap>
                  <Tag color={STATUS_COLOR[row.status]}>
                    {t(`adminUsers.inviteStatus.${row.status}`)}
                  </Tag>
                  <Text code>{row.code}</Text>
                </Space>
                <Space size={4}>
                  <Button
                    type="text"
                    size="small"
                    icon={<Copy size={14} />}
                    onClick={() => void onCopy(row)}
                    title={t("adminUsers.inviteCopyUrl")}
                  />
                  {row.status === "pending" ? (
                    <Popconfirm
                      title={t("adminUsers.inviteRevokeConfirm")}
                      onConfirm={() => void onRevoke(row)}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<Trash2 size={14} />}
                        title={t("adminUsers.inviteRevoke")}
                      />
                    </Popconfirm>
                  ) : null}
                </Space>
              </div>
              <div className={styles.inviteUrlRow}>
                <Link2 size={12} />
                <Text
                  ellipsis
                  className={styles.inviteUrl}
                  title={localInviteUrl(row.code)}
                >
                  {localInviteUrl(row.code)}
                </Text>
              </div>
              {row.note ? (
                <Text type="secondary" className={styles.inviteNote}>
                  {row.note}
                </Text>
              ) : null}
              <div className={styles.inviteMeta}>
                <Text type="secondary">
                  {t("adminUsers.inviteCreatedAt", {
                    time: formatServerDateTime(row.created_at, timeZone),
                  })}
                </Text>
                <Text type="secondary">
                  {t("adminUsers.inviteExpiresAt", {
                    time: formatServerDateTime(row.expires_at, timeZone),
                  })}
                </Text>
              </div>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}
