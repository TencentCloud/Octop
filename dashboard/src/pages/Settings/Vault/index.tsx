import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Dropdown, Input, Popconfirm, Typography } from "antd";
import {
  ChevronDown,
  CreditCard,
  KeyRound,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  User,
} from "lucide-react";
import { message } from "@/utils/antdMessage";
import PageShell from "../../../layouts/PageShell";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { apiErrorMessage } from "../../../utils/apiError";
import {
  vaultApi,
  type VaultItem,
  type VaultItemType,
} from "../../../api/modules/vault";
import CreateVaultItemModal from "./CreateVaultItemModal";

const { Text } = Typography;

import styles from "./Vault.module.less";

const TYPE_ICONS: Record<VaultItemType, typeof KeyRound> = {
  login: KeyRound,
  card: CreditCard,
  contact: User,
};

const ITEM_TYPES: VaultItemType[] = ["login", "card", "contact"];
const FILTERS = ["all", ...ITEM_TYPES] as const;
type VaultFilter = (typeof FILTERS)[number];

function isItemType(value: string): value is VaultItemType {
  return (ITEM_TYPES as string[]).includes(value);
}

/** User-scoped vault management: filter, search, create, and delete. */
export default function VaultPage() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [items, setItems] = useState<VaultItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [filter, setFilter] = useState<VaultFilter>("all");
  const [search, setSearch] = useState("");
  const [createType, setCreateType] = useState<VaultItemType | null>(null);
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

  const counts = useMemo(() => {
    const byType: Record<VaultFilter, number> = {
      all: 0,
      login: 0,
      card: 0,
      contact: 0,
    };
    for (const item of items ?? []) {
      byType.all += 1;
      byType[item.item_type] += 1;
    }
    return byType;
  }, [items]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (items ?? []).filter((item) => {
      if (filter !== "all" && item.item_type !== filter) return false;
      if (!query) return true;
      const haystack = [
        item.title,
        item.origin ?? "",
        ...Object.values(item.fields ?? {}),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [items, filter, search]);

  const filterLabel = (value: VaultFilter) =>
    value === "all" ? t("vault.filter.all") : t(`vault.itemType.${value}`);

  const newItemMenu = {
    items: ITEM_TYPES.map((type) => ({
      key: type,
      icon: (() => {
        const Icon = TYPE_ICONS[type];
        return <Icon size={14} />;
      })(),
      label: t(`vault.itemType.${type}`),
    })),
    onClick: ({ key }: { key: string }) => {
      if (isItemType(key)) setCreateType(key);
    },
  };

  return (
    <PageShell
      title={t("pageShell.vault.title")}
      subtitle={t("pageShell.vault.subtitle")}
      actions={
        <Dropdown trigger={["click"]} menu={newItemMenu}>
          <Button
            type="primary"
            className={styles.newItemButton}
            icon={<Plus size={14} />}
          >
            {t("vault.newItem")}
            <ChevronDown size={14} />
          </Button>
        </Dropdown>
      }
    >
      {error ? (
        <Text type="danger" style={{ display: "block", marginBottom: 12 }}>
          {error}
        </Text>
      ) : null}
      {items !== null ? (
        <div className={styles.toolbar}>
          <div
            className={styles.filterTabs}
            role="group"
            aria-label={t("vault.filter.all")}
          >
            {FILTERS.map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={filter === value}
                className={`${styles.filterPill} ${
                  filter === value ? styles.active : ""
                }`}
                onClick={() => setFilter(value)}
              >
                {filterLabel(value)}
                <span className={styles.count}>{counts[value]}</span>
              </button>
            ))}
          </div>
          <div className={styles.searchWrap}>
            <Input
              allowClear
              prefix={<Search size={14} />}
              placeholder={t("vault.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
      ) : null}
      {error ? null : items === null ? (
        <Text type="secondary">{t("vault.loading")}</Text>
      ) : (items ?? []).length === 0 ? (
        <Text type="secondary">{t("vault.empty")}</Text>
      ) : filtered.length === 0 ? (
        <Text type="secondary">{t("vault.noMatch")}</Text>
      ) : (
        <ul className={styles.list}>
          {filtered.map((item) => {
            const Icon = TYPE_ICONS[item.item_type];
            const revealed = Object.values(item.fields ?? {})
              .filter(Boolean)
              .join(" · ");
            return (
              <li key={item.vault_item_id} className={styles.row}>
                <span
                  className={`${styles.iconBadge} ${styles[item.item_type]}`}
                >
                  <Icon size={16} />
                </span>
                <div className={styles.main}>
                  <div className={styles.titleRow}>
                    <span className={styles.title}>{item.title}</span>
                    <span
                      className={`${styles.typeTag} ${styles[item.item_type]}`}
                    >
                      {t(`vault.itemType.${item.item_type}`)}
                    </span>
                  </div>
                  <div className={styles.metaRow}>
                    {revealed ? (
                      <>
                        <span className={styles.revealed} title={revealed}>
                          {revealed}
                        </span>
                        <span className={styles.dot}>·</span>
                      </>
                    ) : null}
                    {item.origin ? (
                      <>
                        <span className={styles.origin}>{item.origin}</span>
                        <span className={styles.unverified}>
                          {t("vault.originUnverified")}
                        </span>
                        <span className={styles.dot}>·</span>
                      </>
                    ) : null}
                    <span>
                      {t("vault.updatedAt", {
                        time: formatServerDateTime(item.updated_at, timeZone),
                      })}
                    </span>
                  </div>
                </div>
                <Popconfirm
                  title={t("vault.deleteConfirmTitle")}
                  description={t("vault.deleteConfirmDesc", {
                    title: item.title,
                  })}
                  okText={t("vault.deleteConfirmOk")}
                  cancelText={t("vault.deleteCancel")}
                  onConfirm={() => void remove(item)}
                >
                  <button
                    type="button"
                    className={styles.deleteButton}
                    aria-label={t("vault.deleteLabel", { title: item.title })}
                    disabled={deletingId === item.vault_item_id}
                  >
                    <Trash2 size={15} />
                  </button>
                </Popconfirm>
              </li>
            );
          })}
        </ul>
      )}
      <div className={styles.footnote}>
        <ShieldCheck size={13} className={styles.footnoteIcon} />
        {t("vault.privacyNote")}
      </div>
      <CreateVaultItemModal
        itemType={createType}
        onClose={() => setCreateType(null)}
        onCreated={() => void load()}
      />
    </PageShell>
  );
}
