import { Button } from "antd";
import { message } from "@/utils/antdMessage";
import { modal } from "@/utils/antdModal";

import { Activity, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  connectorsApi,
  type ConnectorCatalogEntry,
  type ConnectorInstance,
} from "../../../api/modules/connectors";
import { ConnectorLogo, connectorAccent } from "./connectorDefs";
import styles from "./index.module.less";

interface ConnectorInstanceCardProps {
  instance: ConnectorInstance;
  catalogEntry: ConnectorCatalogEntry | undefined;
  onDeleted: () => void | Promise<void>;
}

export function ConnectorInstanceCard({
  instance,
  catalogEntry,
  onDeleted,
}: ConnectorInstanceCardProps) {
  const { t } = useTranslation();
  const accent = catalogEntry ? connectorAccent(catalogEntry) : "#8c8c8c";

  const handleTest = async () => {
    try {
      const r = await connectorsApi.testInstance(instance.instance_id);
      if (r.ok) message.success(t("connectors.testOk", "连接正常"));
      else message.error(r.error ?? t("connectors.testFailed", "测试失败"));
    } catch (e) {
      console.error(e);
      message.error(t("connectors.testFailed", "测试失败"));
    }
  };

  const handleDelete = () => {
    modal.confirm({
      title: t("connectors.deleteConfirm", { name: instance.display_name }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        await connectorsApi.deleteInstance(instance.instance_id);
        message.success(t("connectors.deleteSuccess", "已删除"));
        await onDeleted();
      },
    });
  };

  return (
    <div
      className={styles.instanceCard}
      style={{ "--connector-accent": accent } as React.CSSProperties}
    >
      <div className={styles.instanceCardMain}>
        <div
          className={styles.instanceCardIcon}
          style={{ color: accent, background: `${accent}18` }}
        >
          <ConnectorLogo kind={instance.kind} icon={catalogEntry?.icon} />
        </div>
        <div className={styles.instanceCardMeta}>
          <div className={styles.instanceCardName}>{instance.display_name}</div>
          <div className={styles.instanceCardKind}>
            {catalogEntry?.name ?? instance.kind}
          </div>
        </div>
      </div>
      <div className={styles.instanceCardActions}>
        <Button
          size="small"
          icon={<Activity size={14} />}
          onClick={() => void handleTest()}
        >
          {t("connectors.test", "测试")}
        </Button>
        <Button
          size="small"
          danger
          icon={<Trash2 size={14} />}
          onClick={handleDelete}
        />
      </div>
    </div>
  );
}
