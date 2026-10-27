import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Empty, Input, Result, Tag } from "antd";
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
import { OctopEmptyMascot } from "../../../components/EmptyState";
import { CardSkeleton } from "../../../components/Skeleton";
import { apiErrorMessage } from "../../../utils/apiError";
import { isCatalogNetworkError } from "../../../utils/networkError";
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

export function PluginMarketPanel() {
  const { t } = useTranslation();
  const [items, setItems] = useState<MarketPlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [networkFailure, setNetworkFailure] = useState(false);
  const itemsRef = useRef(items);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [activeGroup, setActiveGroup] = useState<string>(GROUP_ALL);
  const [keyword, setKeyword] = useState("");
  itemsRef.current = items;

  const fetchMarket = useCallback(
    async (force = false) => {
      if (force) setRefreshing(true);
      else setLoading(true);
      try {
        const rows = await pluginsApi.listMarket();
        setItems(rows);
        setLoadFailed(false);
        setNetworkFailure(false);
      } catch (err) {
        const network = isCatalogNetworkError(err, "NETWORK_ERROR");
        setNetworkFailure(network);
        setLoadFailed(true);
        if (itemsRef.current.length > 0) {
          message.error(
            network
              ? t("apiErrors.NETWORK_ERROR")
              : t("plugins.marketUnavailable"),
          );
        }
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

  const handleInstall = async (row: MarketPlugin) => {
    setInstallingId(row.id);
    try {
      await pluginsApi.installFromMarket(row.id, row.version);
      message.success(
        row.update_available
          ? t("plugins.marketUpdateSuccess")
          : t("plugins.installSuccess"),
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

  const catalogFailed = loadFailed && items.length === 0;

  return (
    <div className={styles.panel}>
      {!catalogFailed && (
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            {loading ? null : (
              <span className={styles.toolbarCount}>
                {t("plugins.totalMarket", { count: filtered.length })}
              </span>
            )}
          </div>
          <div
            className={`${styles.toolbarRight} ${styles.marketToolbarRight}`}
          >
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
      )}

      {!catalogFailed && !keyword.trim() && groupOptions.length > 1 ? (
        <div className={styles.groupTabsWrap}>
          {groupOptions.map((opt) => {
            const active = activeGroup === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                aria-pressed={active}
                className={
                  active
                    ? `${styles.groupPill} ${styles.groupPillActive}`
                    : styles.groupPill
                }
                onClick={() => setActiveGroup(opt.value)}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      ) : null}

      {loading ? (
        <div className={styles.loadingSkeleton}>
          <CardSkeleton
            count={6}
            containerStyle={{
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              rowGap: 16,
              columnGap: 12,
              padding: "4px 0 24px",
            }}
          />
        </div>
      ) : catalogFailed ? (
        <div className={styles.marketStage}>
          <Result
            className={styles.marketLoadResult}
            icon={<OctopEmptyMascot size={120} />}
            title={t("plugins.marketLoadError")}
            subTitle={
              networkFailure
                ? t("apiErrors.NETWORK_ERROR")
                : t("plugins.marketUnavailable")
            }
            extra={
              <Button
                type="primary"
                loading={refreshing}
                onClick={() => void fetchMarket(true)}
              >
                {t("common.retry")}
              </Button>
            }
          />
        </div>
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
                      crossOrigin="anonymous"
                      fadeIn
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
                      onClick={() => void handleInstall(row)}
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
                      onClick={() => void handleInstall(row)}
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
