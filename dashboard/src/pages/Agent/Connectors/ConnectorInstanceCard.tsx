import { App, Switch, Tag, Tooltip } from "antd";

import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  connectorsApi,
  type ConnectorCatalogEntry,
  type ConnectorInstance,
} from "../../../api/modules/connectors";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { ConnectorLogo, connectorAccent } from "./connectorDefs";
import styles from "./index.module.less";

interface ConnectorInstanceCardProps {
  instance: ConnectorInstance;
  catalogEntry: ConnectorCatalogEntry | undefined;
  onEdit: (instance: ConnectorInstance) => void;
  onChanged: () => void | Promise<void>;
}

export function ConnectorInstanceCard({
  instance,
  catalogEntry,
  onEdit,
  onChanged,
}: ConnectorInstanceCardProps) {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const user = useCurrentUser();
  const accent = catalogEntry ? connectorAccent(catalogEntry) : "#8c8c8c";
  const isOwner = user?.id === instance.owner_user_id;
  const ownerLabel =
    instance.owner_display_name || instance.owner_username || "";
  const editable =
    instance.can_manage &&
    (catalogEntry != null || (instance.kind === "custom-mcp" && isOwner));

  const handleDelete = () => {
    modal.confirm({
      title: t("connectors.deleteConfirm", { name: instance.display_name }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        await connectorsApi.deleteInstance(instance.instance_id);
        message.success(t("connectors.deleteSuccess", "已删除"));
        await onChanged();
      },
    });
  };

  const handleToggle = async (enabled: boolean) => {
    try {
      await connectorsApi.patchInstance(instance.instance_id, {
        status: enabled ? "active" : "disabled",
      });
      message.success(
        enabled
          ? t("connectors.enableSuccess", "已启用")
          : t("connectors.disableSuccess", "已停用"),
      );
      await onChanged();
    } catch (error) {
      console.error(error);
      message.error(t("connectors.toggleFailed", "更新失败"));
    }
  };

  return (
    <div
      className={styles.typeCard}
      style={{ "--connector-accent": accent } as React.CSSProperties}
      onClick={() => editable && onEdit(instance)}
      role={editable ? "button" : undefined}
      tabIndex={editable ? 0 : -1}
      onKeyDown={(e) => e.key === "Enter" && editable && onEdit(instance)}
    >
      <div className={styles.typeCardBody}>
        <div className={styles.typeCardHeader}>
          <div className={styles.typeCardIconLarge}>
            <ConnectorLogo
              kind={instance.kind}
              icon={catalogEntry?.icon}
              size={40}
            />
          </div>
          <div className={styles.typeCardTitle}>{instance.display_name}</div>
          <div
            className={styles.instanceCardHeaderActions}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            {instance.shared ? (
              <Tag color="blue" className={styles.instanceCardTag}>
                {isOwner || !ownerLabel
                  ? t("connectors.sharedBadge", "共享")
                  : t("connectors.sharedFrom", {
                      name: ownerLabel,
                      defaultValue: `来自 ${ownerLabel}`,
                    })}
              </Tag>
            ) : null}
            {instance.can_manage ? (
              <Switch
                size="small"
                checked={instance.status === "active"}
                onChange={(enabled) => void handleToggle(enabled)}
              />
            ) : null}
          </div>
        </div>

        <div className={styles.typeCardDesc}>
          {instance.description ||
            catalogEntry?.description ||
            catalogEntry?.name ||
            instance.kind}
        </div>
      </div>

      <div className={styles.typeCardFooter}>
        <div className={styles.typeCardHint}>
          {!instance.has_credentials
            ? t("connectors.noCredentials", "缺少凭证")
            : editable
            ? t("connectors.clickToManage", "点击管理连接")
            : t("connectors.sharedReadonly", "共享连接器，仅所有者可管理")}
        </div>
        {instance.can_manage ? (
          <div
            className={styles.instanceCardActions}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <Tooltip title={t("common.delete")} mouseEnterDelay={0.5}>
              <button
                type="button"
                className={styles.instanceCardDelBtn}
                onClick={handleDelete}
                aria-label={t("common.delete")}
              >
                <Trash2 size={13} />
              </button>
            </Tooltip>
          </div>
        ) : null}
      </div>
    </div>
  );
}
