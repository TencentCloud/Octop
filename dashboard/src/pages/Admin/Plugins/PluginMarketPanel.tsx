import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Empty, Input, Segmented, Tag } from "antd";
import { message } from "@/utils/antdMessage";
import {
  ArrowUpCircle,
  Check,
  Download,
  RefreshCw,
  Search,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { pluginsApi, type MarketPlugin } from "../../../api/modules/plugins";
import { CardSkeleton } from "../../../components/Skeleton";
import { apiErrorMessage } from "../../../utils/apiError";
import styles from "./index.module.less";
import { PluginIconView } from "./PluginIconView";
import { PluginCardMeta } from "./PluginCardMeta";
import { PLUGIN_GROUP_ORDER, isKnownPluginGroup } from "./pluginGroups";
import { notifyPluginsChanged } from "./pluginsEvents";

const GROUP_ALL = "all";

function matchesMarketQuery(row: MarketPlugin, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    row.id,
    row.name,
    row.description,
    row.kind,
    row.group,
    row.version,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

/** Marketplace catalog — install copies in-tree packages to ~/.octop/plugins. */
export function PluginMarketPanel() {
  const { t } = useTranslation();
  const [items, setItems] = useState<MarketPlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [activeGroup, setActiveGroup] = useState<string>(GROUP_ALL);
  const [keyword, setKeyword] = useState("");

  const fetchMarket = useCallback(
    async (force = false) => {
      if (force) setRefreshing(true);
      else setLoading(true);
      try {
        const rows = await pluginsApi.listMarket();
        setItems(rows);
      } catch (err) {
        message.error(apiErrorMessage(err, t("plugins.marketLoadError"), t));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchMarket();
  }, [fetchMarket]);

  const handleInstall = async (row: MarketPlugin, force: boolean) => {
    setInstallingId(row.id);
    try {
      await pluginsApi.installFromMarket(row.id, force);
      message.success(
        force ? t("plugins.marketUpdateSuccess") : t("plugins.installSuccess"),
      );
      notifyPluginsChanged();
      await fetchMarket(true);
    } catch (err) {
      message.error(apiErrorMessage(err, t("plugins.installFailed"), t));
    } finally {
      setInstallingId(null);
    }
  };

  const groupOptions = useMemo(() => {
    const present = new Set<string>();
    for (const row of items) {
      const g = (row.group || "").trim().toLowerCase();
      if (g) present.add(g);
    }
    const ordered = PLUGIN_GROUP_ORDER.filter((g) => present.has(g));
    const extras = [...present]
      .filter((g) => !isKnownPluginGroup(g))
      .sort((a, b) => a.localeCompare(b));
    return [
      { value: GROUP_ALL, label: t("plugins.groupAll") },
      ...ordered.map((g) => ({
        value: g,
        label: t(`plugins.groups.${g}`),
      })),
      ...extras.map((g) => ({
        value: g,
        label: t("plugins.groupUnknown"),
      })),
    ];
  }, [items, t]);

  const filtered = useMemo(() => {
    const byGroup =
      keyword.trim() || activeGroup === GROUP_ALL
        ? items
        : items.filter(
            (row) => (row.group || "").trim().toLowerCase() === activeGroup,
          );
    if (!keyword.trim()) return byGroup;
    return byGroup.filter((row) => matchesMarketQuery(row, keyword));
  }, [activeGroup, items, keyword]);

  useEffect(() => {
    if (
      activeGroup !== GROUP_ALL &&
      !groupOptions.some((opt) => opt.value === activeGroup)
    ) {
      setActiveGroup(GROUP_ALL);
    }
  }, [activeGroup, groupOptions]);

  return (
    <div className={styles.panel}>
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <span className={styles.toolbarCount}>
            {t("plugins.totalMarket", { count: filtered.length })}
          </span>
        </div>
        <div className={`${styles.toolbarRight} ${styles.marketToolbarRight}`}>
          <Input
            className={styles.marketSearch}
            prefix={<Search size={14} />}
            allowClear
            value={keyword}
            placeholder={t("plugins.marketSearchPlaceholder")}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Button
            icon={<RefreshCw size={14} />}
            loading={refreshing}
            onClick={() => void fetchMarket(true)}
          >
            {t("plugins.marketRefresh")}
          </Button>
        </div>
      </div>

      {!keyword.trim() && groupOptions.length > 1 ? (
        <div className={styles.groupTabsWrap}>
          <Segmented
            block
            size="large"
            value={activeGroup}
            onChange={(v) => setActiveGroup(String(v))}
            options={groupOptions}
            className={styles.groupTabs}
          />
        </div>
      ) : null}

      {loading ? (
        <CardSkeleton count={6} />
      ) : filtered.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            items.length === 0
              ? t("plugins.marketEmpty")
              : keyword.trim()
              ? t("plugins.marketSearchEmpty")
              : t("plugins.emptyGroup")
          }
        />
      ) : (
        <div className={styles.cardGrid}>
          {filtered.map((row) => {
            const installed = !!row.installed;
            const canUpdate = !!row.update_available;
            return (
              <article
                key={row.id}
                className={`${styles.card} ${
                  installed ? styles.cardInstalled : ""
                }`}
              >
                <div className={styles.cardBody}>
                  <div className={styles.cardTop}>
                    <PluginIconView
                      icon={row.icon}
                      size={32}
                      className={styles.cardIcon}
                    />
                    <div className={styles.cardTitleCol}>
                      <h3 className={styles.cardName}>{row.name || row.id}</h3>
                      <PluginCardMeta
                        kind={row.kind}
                        group={row.group}
                        version={row.version}
                        trailing={
                          canUpdate ? (
                            <Tag color="processing" bordered={false}>
                              {t("plugins.marketUpdateAvailable")}
                            </Tag>
                          ) : installed ? (
                            <Tag color="success" bordered={false}>
                              {t("plugins.marketInstalled")}
                            </Tag>
                          ) : null
                        }
                      />
                    </div>
                  </div>
                  <p className={styles.cardDesc}>
                    {row.error || row.description || t("plugins.noDescription")}
                  </p>
                </div>
                <div className={styles.cardFooter}>
                  <span className={styles.tableMono}>{row.id}</span>
                  <span className={styles.cardFooterSpacer} />
                  {canUpdate ? (
                    <Button
                      type="primary"
                      size="small"
                      icon={<ArrowUpCircle size={14} />}
                      loading={installingId === row.id}
                      onClick={() => void handleInstall(row, true)}
                    >
                      {t("plugins.marketUpdate")}
                    </Button>
                  ) : installed ? (
                    <Button size="small" icon={<Check size={14} />} disabled>
                      {t("plugins.marketInstalled")}
                    </Button>
                  ) : (
                    <Button
                      type="primary"
                      size="small"
                      icon={<Download size={14} />}
                      loading={installingId === row.id}
                      onClick={() => void handleInstall(row, false)}
                    >
                      {t("plugins.marketInstall")}
                    </Button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
