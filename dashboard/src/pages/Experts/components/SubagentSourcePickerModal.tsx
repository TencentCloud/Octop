import { useEffect, useMemo, useState } from "react";
import { Button, Drawer, Empty, Input, List, Spin } from "antd";
import { useTranslation } from "react-i18next";

import {
  getSubagentCatalogItem,
  listSubagentCatalog,
  type SubagentCatalogItem,
} from "../../../api/modules/subagents";
import { apiErrorMessage } from "../../../utils/apiError";
import { normalizeUiLocale } from "../../../utils/locale";
import { pickLocale } from "../../../utils/localizedText";
import { message } from "@/utils/antdMessage";

export interface PickedCatalogSubagent {
  slug: string;
  name: string;
  description: string;
  content: string;
}

interface SubagentSourcePickerModalProps {
  open: boolean;
  excludeSlugs: ReadonlySet<string>;
  onClose: () => void;
  onPick: (subagent: PickedCatalogSubagent) => void;
}

export default function SubagentSourcePickerModal({
  open,
  excludeSlugs,
  onClose,
  onPick,
}: SubagentSourcePickerModalProps) {
  const { t, i18n } = useTranslation();
  const lang = normalizeUiLocale(i18n.language);
  const [items, setItems] = useState<SubagentCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [pickingSlug, setPickingSlug] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    let cancelled = false;
    setLoading(true);
    void listSubagentCatalog()
      .then((rows) => {
        if (!cancelled) setItems(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setItems([]);
          message.error(apiErrorMessage(err, t("subagents.loadFailed"), t));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, t]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      if (excludeSlugs.has(item.slug)) return false;
      if (!q) return true;
      const name = pickLocale(item.name, lang);
      const desc = pickLocale(item.description, lang);
      return (
        item.slug.toLowerCase().includes(q) ||
        name.toLowerCase().includes(q) ||
        desc.toLowerCase().includes(q)
      );
    });
  }, [excludeSlugs, items, lang, query]);

  const handlePick = async (item: SubagentCatalogItem) => {
    setPickingSlug(item.slug);
    try {
      const detail = await getSubagentCatalogItem(item.slug);
      onPick({
        slug: item.slug,
        name: pickLocale(item.name, lang) || item.slug,
        description: pickLocale(item.description, lang),
        content: pickLocale(detail.content, lang),
      });
      onClose();
    } catch (err) {
      message.error(apiErrorMessage(err, t("experts.copySubagentFailed"), t));
    } finally {
      setPickingSlug(null);
    }
  };

  return (
    <Drawer
      open={open}
      title={t("experts.addSubagentTitle")}
      width={560}
      onClose={onClose}
      destroyOnHidden
    >
      <Input
        allowClear
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("subagents.searchPlaceholder")}
        style={{ marginBottom: 16 }}
      />
      {loading ? (
        <div style={{ textAlign: "center", padding: 32 }}>
          <Spin />
        </div>
      ) : filtered.length === 0 ? (
        <Empty description={t("experts.noSubagentCatalog")} />
      ) : (
        <List
          dataSource={filtered}
          renderItem={(item) => {
            const name = pickLocale(item.name, lang) || item.slug;
            return (
              <List.Item
                key={item.slug}
                actions={[
                  <Button
                    key="pick"
                    type="link"
                    loading={pickingSlug === item.slug}
                    onClick={() => void handlePick(item)}
                  >
                    {t("experts.pickSkill")}
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={`${item.emoji ? `${item.emoji} ` : ""}${name}`}
                  description={pickLocale(item.description, lang) || item.slug}
                />
              </List.Item>
            );
          }}
        />
      )}
    </Drawer>
  );
}
