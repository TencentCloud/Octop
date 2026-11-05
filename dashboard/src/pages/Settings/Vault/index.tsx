import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, List, Popconfirm, Tag, Typography } from "antd";
import { KeyRound, Trash2 } from "lucide-react";
import { message } from "@/utils/antdMessage";
import PageShell from "../../../layouts/PageShell";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { apiErrorMessage } from "../../../utils/apiError";
import { vaultApi, type VaultItem } from "../../../api/modules/vault";

const { Text } = Typography;

const itemTypeTagColor: Record<string, string> = {
  login: "blue",
  card: "purple",
  contact: "green",
};

/** User-scoped vault management: list and delete, metadata only. */
export default function VaultPage() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [items, setItems] = useState<VaultItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // Keep `t` out of the loader's deps: i18next returns a fresh function per
  // render in tests, which would refetch the list on every state change.
  const tRef = useRef(t);
  tRef.current = t;

  const load = useCallback(async () => {
    setError(null);
    try {
      const response = await vaultApi.list();
      setItems(response.items);
    } catch (err) {
      setError(
        apiErrorMessage(err, tRef.current("vault.loadFailed"), tRef.current),
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (item: VaultItem) => {
    setDeletingId(item.vault_item_id);
    try {
      await vaultApi.remove(item.vault_item_id);
      message.success(t("vault.deleted", { title: item.title }));
      await load();
    } catch (err) {
      message.error(apiErrorMessage(err, t("vault.deleteFailed"), t));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <PageShell
      title={t("pageShell.vault.title")}
      subtitle={t("pageShell.vault.subtitle")}
    >
      {error ? (
        <Text type="danger" style={{ display: "block", marginBottom: 12 }}>
          {error}
        </Text>
      ) : null}
      <List
        loading={items === null && !error}
        dataSource={items ?? []}
        locale={{ emptyText: t("vault.empty") }}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Popconfirm
                key="delete"
                title={t("vault.deleteConfirmTitle")}
                description={t("vault.deleteConfirmDesc", {
                  title: item.title,
                })}
                okText={t("vault.deleteConfirmOk")}
                cancelText={t("vault.deleteCancel")}
                onConfirm={() => void remove(item)}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  aria-label={t("vault.deleteLabel", { title: item.title })}
                  icon={<Trash2 size={14} />}
                  loading={deletingId === item.vault_item_id}
                />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              avatar={<KeyRound size={16} />}
              title={
                <span>
                  {item.title}{" "}
                  <Tag color={itemTypeTagColor[item.item_type]}>
                    {t(`vault.itemType.${item.item_type}`)}
                  </Tag>
                </span>
              }
              description={
                <span>
                  {item.origin ? (
                    <Text type="secondary" style={{ marginRight: 8 }}>
                      {item.origin}
                      <Text
                        type="secondary"
                        italic
                        style={{ marginLeft: 6, fontSize: 12 }}
                      >
                        {t("vault.originUnverified")}
                      </Text>
                    </Text>
                  ) : null}
                  <Text type="secondary">
                    {t("vault.updatedAt", {
                      time: formatServerDateTime(item.updated_at, timeZone),
                    })}
                  </Text>
                </span>
              }
            />
          </List.Item>
        )}
      />
    </PageShell>
  );
}
