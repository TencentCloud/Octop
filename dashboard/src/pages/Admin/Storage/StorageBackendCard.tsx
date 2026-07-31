/**
 * StorageBackendCard — display card for one configured StorageBackendRow in the my-storage tab.
 *
 * Shows type icon (from STORAGE_TYPE_DEFS), name, kind, bucket/region/key info,
 * enabled toggle, edit and delete actions.
 */
import { useState } from "react";
import { Button, Modal, Switch, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";

import {
  Pencil,
  Trash2,
  CheckCircle,
  AlertCircle,
  Activity,
  FolderOpen,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import {
  STORAGE_TYPE_DEFS,
  type StorageBackendRow,
} from "./useStorageBackends";
import { StorageBackendDrawer } from "./StorageBackendModal";
import { StorageBrowseDrawer } from "./StorageBrowseDrawer";
import styles from "./storage.module.less";

interface StorageBackendCardProps {
  backend: StorageBackendRow;
  onSaved: () => void | Promise<void>;
  isNew?: boolean;
}

export function StorageBackendCard({
  backend,
  onSaved,
  isNew,
}: StorageBackendCardProps) {
  const { t } = useTranslation();
  const [editOpen, setEditOpen] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [testing, setTesting] = useState(false);

  // Find matching type def for icon + color
  const typeDef = STORAGE_TYPE_DEFS.find((d) => d.kind === backend.kind);
  const accent = typeDef?.color ?? "#8c8c8c";
  const icon = typeDef?.icon ?? null;

  const handleToggle = async (next: boolean) => {
    setToggling(true);
    try {
      await request(`/admin/storage-backends/${backend.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: next }),
      });
      await onSaved();
    } catch {
      message.error(t("storage.toggleFailed"));
    } finally {
      setToggling(false);
    }
  };

  const handleDelete = () => {
    Modal.confirm({
      title: t("storage.deleteTitle"),
      content: t("storage.deleteConfirm", { name: backend.name }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await request(`/admin/storage-backends/${backend.id}`, {
            method: "DELETE",
          });
          message.success(t("storage.deleteSuccess", { name: backend.name }));
          await onSaved();
        } catch (err) {
          message.error(
            err instanceof Error ? err.message : t("common.deleteFailed"),
          );
        }
      },
    });
  };

  const isConfigured = !!backend.access_key || !!backend.bucket;
  const primaryInfo = backend.bucket ?? backend.endpoint ?? "—";

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await request<{
        ok: boolean;
        message?: string;
        message_key?: string;
      }>(`/admin/storage-backends/${backend.id}/test`, { method: "POST" });
      if (result.ok) {
        const msg = result.message_key
          ? t(
              `storage.${result.message_key}`,
              result.message || t("storage.testSuccess"),
            )
          : result.message || t("storage.testSuccess");
        message.success(msg);
      } else {
        message.error(result.message || t("storage.testFailed"));
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("storage.testFailed"),
      );
    } finally {
      setTesting(false);
    }
  };

  return (
    <>
      <div
        className={`${styles.backendCard} ${
          isNew ? styles.backendCardNew : ""
        }`}
        style={{ opacity: backend.enabled ? 1 : 0.65 }}
      >
        {/* Header */}
        <div className={styles.backendCardHeader}>
          <div
            className={styles.backendCardIcon}
            style={{ color: accent, background: `${accent}18` }}
          >
            {icon}
          </div>
          <div className={styles.backendCardTitle}>
            <div className={styles.backendCardName}>{backend.name}</div>
            <div className={styles.backendCardKind}>
              {typeDef ? t(typeDef.nameKey) : backend.kind}
            </div>
          </div>
          <div
            className={
              isConfigured ? styles.statusBadgeOk : styles.statusBadgeNo
            }
          >
            {isConfigured ? (
              <CheckCircle size={11} />
            ) : (
              <AlertCircle size={11} />
            )}
            <span className={styles.statusBadge}>
              {isConfigured
                ? t("storage.configured")
                : t("storage.notConfigured")}
            </span>
          </div>
        </div>

        {/* Info rows */}
        <div className={styles.backendCardInfo}>
          <div className={styles.infoRow}>
            <span className={styles.infoLabel}>
              {t("storage.bucketLabel")}:
            </span>
            <span className={styles.infoValue}>
              {primaryInfo !== "—" ? (
                primaryInfo
              ) : (
                <span className={styles.infoEmpty}>—</span>
              )}
            </span>
          </div>
          {backend.region && (
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>
                {t("storage.regionLabel")}:
              </span>
              <span className={styles.infoValue}>{backend.region}</span>
            </div>
          )}
          {backend.access_key && (
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>Access Key:</span>
              <span className={styles.infoValue}>{backend.access_key}</span>
            </div>
          )}
          {backend.note && (
            <div className={styles.backendCardNote}>{backend.note}</div>
          )}
        </div>

        {/* Actions */}
        <div className={styles.backendCardActions}>
          <div className={styles.backendActionsLeft}>
            <Switch
              size="small"
              checked={backend.enabled}
              loading={toggling}
              onChange={(c) => void handleToggle(c)}
            />
            <span style={{ fontSize: 12, color: "var(--fn-text-tertiary)" }}>
              {backend.enabled ? t("common.enabled") : t("common.disabled")}
            </span>
          </div>
          <div className={styles.backendActionsRight}>
            <Tooltip title={t("storage.browse")}>
              <Button
                type="text"
                size="small"
                icon={<FolderOpen size={14} />}
                aria-label={t("storage.browse")}
                onClick={() => setBrowseOpen(true)}
              />
            </Tooltip>
            <Tooltip title={t("storage.testAvailability")}>
              <Button
                type="text"
                size="small"
                icon={<Activity size={14} />}
                loading={testing}
                aria-label={t("storage.testAvailability")}
                onClick={() => void handleTest()}
              />
            </Tooltip>
            <Tooltip title={t("common.edit")}>
              <Button
                type="text"
                size="small"
                icon={<Pencil size={14} />}
                aria-label={t("common.edit")}
                onClick={() => setEditOpen(true)}
              />
            </Tooltip>
            <Tooltip title={t("common.delete")}>
              <Button
                type="text"
                size="small"
                danger
                icon={<Trash2 size={14} />}
                aria-label={t("common.delete")}
                onClick={handleDelete}
              />
            </Tooltip>
          </div>
        </div>
      </div>

      <StorageBackendDrawer
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onSaved={onSaved}
        editing={backend}
      />

      <StorageBrowseDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        backend={backend}
      />
    </>
  );
}
