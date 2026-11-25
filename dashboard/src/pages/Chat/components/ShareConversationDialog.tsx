import { useCallback, useEffect, useState } from "react";
import { Button, Input, Modal, Popconfirm, Space, Spin } from "antd";
import { useTranslation } from "react-i18next";
import {
  octopThreadsApi,
  type ThreadShareLink,
} from "../../../api/modules/octopThreads";
import { message } from "../../../utils/antdMessage";
import { apiErrorMessage } from "../../../utils/apiError";
import { copyText } from "../../../utils/copyText";
import { publicUrl } from "../../../utils/publicUrl";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import styles from "./ShareConversationDialog.module.less";

function sharePageUrl(shareId: string): string {
  return new URL(publicUrl(`share/${shareId}`), window.location.origin).href;
}

export default function ShareConversationDialog({
  open,
  agentId,
  threadId,
  onClose,
}: {
  open: boolean;
  agentId: string;
  threadId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const timezone = useServerTimezone();
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<ThreadShareLink | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setLink(null);
    octopThreadsApi
      .shareStatus(agentId, threadId)
      .then((status) => {
        if (!cancelled) setLink(status);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          message.error(
            apiErrorMessage(error, t("chat.publicShare.failed"), t),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, agentId, threadId, t]);

  const create = useCallback(
    async (rotate: boolean) => {
      setBusy(true);
      try {
        const status = await octopThreadsApi.createShare(
          agentId,
          threadId,
          rotate,
        );
        setLink(status);
      } catch (error) {
        message.error(apiErrorMessage(error, t("chat.publicShare.failed"), t));
      } finally {
        setBusy(false);
      }
    },
    [agentId, threadId, t],
  );

  const revoke = useCallback(async () => {
    setBusy(true);
    try {
      await octopThreadsApi.revokeShare(agentId, threadId);
      setLink({ active: false });
      message.success(t("chat.publicShare.revoked"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("chat.publicShare.failed"), t));
    } finally {
      setBusy(false);
    }
  }, [agentId, threadId, t]);

  const copy = useCallback(async () => {
    const shareId = link?.share_id;
    if (!shareId) return;
    const ok = await copyText(sharePageUrl(shareId));
    if (ok) message.success(t("chat.publicShare.copied"));
    else message.error(t("chat.publicShare.copyFailed"));
  }, [link?.share_id, t]);

  const url = link?.share_id ? sharePageUrl(link.share_id) : "";
  const active = Boolean(link?.active && link.share_id);
  const createdAt =
    active && link?.created_at
      ? formatServerDateTime(link.created_at, timezone)
      : "";

  return (
    <Modal
      title={t("chat.publicShare.action", "分享链接")}
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnClose
      width={480}
      style={{ top: 48 }}
    >
      <p className={styles.hint}>{t("chat.publicShare.hint")}</p>
      {loading ? (
        <div className={styles.loading}>
          <Spin />
        </div>
      ) : active ? (
        <>
          <Space.Compact block>
            <Input
              value={url}
              readOnly
              aria-label={t("chat.publicShare.action", "分享链接")}
              onFocus={(event) => event.target.select()}
            />
            <Button type="primary" onClick={() => void copy()} disabled={busy}>
              {t("chat.publicShare.copy")}
            </Button>
          </Space.Compact>
          {createdAt ? (
            <p className={styles.meta}>
              {t("chat.publicShare.createdAt", { time: createdAt })}
            </p>
          ) : null}
          <div className={styles.actions}>
            <Popconfirm
              title={t("chat.publicShare.rotateHint")}
              onConfirm={() => void create(true)}
              okText={t("chat.publicShare.rotate")}
              cancelText={t("common.cancel")}
            >
              <Button type="link" disabled={busy}>
                {t("chat.publicShare.rotate")}
              </Button>
            </Popconfirm>
            <Popconfirm
              title={t("chat.publicShare.revokeHint")}
              onConfirm={() => void revoke()}
              okText={t("chat.publicShare.revoke")}
              cancelText={t("common.cancel")}
            >
              <Button type="link" danger disabled={busy}>
                {t("chat.publicShare.revoke")}
              </Button>
            </Popconfirm>
          </div>
        </>
      ) : (
        <Button
          type="primary"
          loading={busy}
          onClick={() => void create(false)}
        >
          {t("chat.publicShare.create")}
        </Button>
      )}
    </Modal>
  );
}
