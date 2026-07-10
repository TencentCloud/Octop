import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Button, Drawer, Input, message, Spin, Tag } from "antd";
import {
  CircleCheck,
  Download,
  Layers,
  RefreshCw,
  Search,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  expertMarketApi,
  type MarketExpert,
} from "../../../api/modules/expertMarket";
import { apiErrorMessage } from "../../../utils/apiError";
import { pickLocale } from "../../../utils/localizedText";
import { iconForName } from "./iconForName";
import styles from "../index.module.less";

interface ExpertMarketTabProps {
  lang: "zh" | "en";
  installedExpertIds: Set<string>;
  onCreated: (agentId: string) => void;
}

function descOf(expert: MarketExpert, lang: "zh" | "en"): string {
  return pickLocale(expert.description, lang) || "";
}

function labelOf(expert: MarketExpert, lang: "zh" | "en"): string {
  return pickLocale(expert.label, lang) || expert.slug;
}

function marketErrorMessage(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message : String(err || "");
  if (raw.includes("404") || raw.includes("Not Found")) {
    return fallback;
  }
  return raw || fallback;
}

export default function ExpertMarketTab({
  lang,
  installedExpertIds,
  onCreated,
}: ExpertMarketTabProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<MarketExpert[]>([]);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<MarketExpert | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [creatingSlug, setCreatingSlug] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchMarket = useCallback(
    async (query = keyword, force = false) => {
      if (force) setRefreshing(true);
      else setLoading(true);
      try {
        const rows = await expertMarketApi.listSkillsets(query);
        setItems(rows ?? []);
        setErrorMessage(null);
      } catch (err) {
        const msg = marketErrorMessage(
          err,
          t("experts.marketBackendMissing"),
        );
        setErrorMessage(msg);
        message.error(msg);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [keyword, t],
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void fetchMarket(keyword);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [keyword, fetchMarket]);

  const openDetail = useCallback(async (expert: MarketExpert) => {
    setSelected(expert);
    setDetailLoading(true);
    try {
      const detail = await expertMarketApi.getSkillset(expert.slug);
      setSelected(detail);
    } catch {
      // The card data is still enough to create; keep the drawer open.
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const createMarketExpert = useCallback(
    async (expert: MarketExpert) => {
      if (installedExpertIds.has(expert.id) || creatingSlug) return;
      setCreatingSlug(expert.slug);
      try {
        const result = await expertMarketApi.createFromSkillset(expert.slug);
        message.success(
          t("experts.marketCreateSuccess", { name: result.name }),
        );
        setSelected(null);
        onCreated(result.agent_id);
      } catch (err) {
        message.error(apiErrorMessage(err, t("experts.createFailed"), t));
      } finally {
        setCreatingSlug(null);
      }
    },
    [creatingSlug, installedExpertIds, onCreated, t],
  );

  const totalText = useMemo(
    () => t("experts.totalMarket", { count: items.length }),
    [items.length, t],
  );

  if (loading && items.length === 0) {
    return (
      <div className={styles.loadingState}>
        <Spin />
      </div>
    );
  }

  return (
    <div className={styles.marketContainer}>
      <div className={styles.gridToolbar}>
        <span className={styles.gridCount}>{totalText}</span>
        <div className={styles.gridToolbarRight}>
          <Input
            className={styles.marketSearch}
            prefix={<Search size={14} />}
            allowClear
            value={keyword}
            placeholder={t("experts.marketSearchPlaceholder")}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <button
            className={styles.toolbarIconBtn}
            disabled={refreshing}
            onClick={() => void fetchMarket(keyword, true)}
            type="button"
          >
            <RefreshCw
              size={14}
              className={refreshing ? styles.spinning : undefined}
            />
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className={styles.emptyState}>
          <Layers size={48} style={{ color: "var(--fn-text-tertiary)" }} />
          <div className={styles.emptyTitle}>
            {errorMessage
              ? t("experts.marketLoadFailed")
              : t("experts.emptyMarket")}
          </div>
          <div className={styles.emptyHint}>
            {errorMessage || t("experts.emptyMarketHint")}
          </div>
          {errorMessage && (
            <div className={styles.emptyActions}>
              <button
                className={styles.emptyAction}
                onClick={() => void fetchMarket(keyword, true)}
                type="button"
              >
                {t("common.refresh")}
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className={styles.cardGrid}>
          {items.map((expert) => {
            const installed = installedExpertIds.has(expert.id);
            const label = labelOf(expert, lang);
            const desc = descOf(expert, lang);
            const accent = expert.color || "#6366f1";
            return (
              <div
                key={expert.id}
                className={styles.expertTemplateCard}
                onClick={() => void openDetail(expert)}
                style={
                  {
                    "--expert-accent": accent,
                  } as CSSProperties
                }
              >
                {installed && (
                  <div className={styles.expertInstalledCheck}>
                    <CircleCheck size={16} />
                  </div>
                )}
                <div className={styles.agentCardHeader}>
                  <div
                    className={styles.agentCardIcon}
                    style={{
                      color: accent,
                      background: `${accent}18`,
                    }}
                  >
                    {expert.icon_url ? (
                      <img
                        src={expert.icon_url}
                        alt=""
                        className={styles.marketIconImg}
                      />
                    ) : (
                      iconForName(expert.icon_name || "zap", 20)
                    )}
                  </div>
                  <div className={styles.agentCardTitleBlock}>
                    <div className={styles.agentCardName}>{label}</div>
                    {installed && (
                      <div className={styles.expertInstalledLabel}>
                        {t("experts.installedBadge")}
                      </div>
                    )}
                  </div>
                </div>
                <div className={styles.agentCardDesc}>
                  {desc || t("experts.noMarketDescription")}
                </div>
                <div className={styles.marketCardFooter}>
                  <span className={styles.marketMeta}>
                    <Zap size={13} />
                    {t("experts.marketSkillCount", {
                      count:
                        expert.skill_count ?? expert.skill_slugs?.length ?? 0,
                    })}
                  </span>
                  <Button
                    size="small"
                    type={installed ? "default" : "primary"}
                    icon={
                      installed ? (
                        <CircleCheck size={14} />
                      ) : (
                        <Download size={14} />
                      )
                    }
                    loading={creatingSlug === expert.slug}
                    disabled={installed || Boolean(creatingSlug)}
                    onClick={(e) => {
                      e.stopPropagation();
                      void createMarketExpert(expert);
                    }}
                  >
                    {installed
                      ? t("experts.installedBadge")
                      : t("experts.createFromMarket")}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Drawer
        open={!!selected}
        width={560}
        destroyOnClose
        onClose={() => setSelected(null)}
        title={selected ? labelOf(selected, lang) : ""}
        footer={
          selected ? (
            <Button
              type="primary"
              size="large"
              block
              icon={<Download size={14} />}
              loading={creatingSlug === selected.slug}
              disabled={
                installedExpertIds.has(selected.id) || Boolean(creatingSlug)
              }
              onClick={() => void createMarketExpert(selected)}
            >
              {installedExpertIds.has(selected.id)
                ? t("experts.installedBadge")
                : t("experts.createFromMarket")}
            </Button>
          ) : null
        }
      >
        {selected && (
          <div className={styles.marketDrawerBody}>
            <div className={styles.marketTagRow}>
              <Tag bordered={false}>{t("experts.marketSource")}</Tag>
              {selected.scene && <Tag bordered={false}>{selected.scene}</Tag>}
              {selected.sub_scene && (
                <Tag bordered={false}>{selected.sub_scene}</Tag>
              )}
              <Tag bordered={false}>
                {t("experts.marketSkillCount", {
                  count:
                    selected.skill_count ?? selected.skill_slugs?.length ?? 0,
                })}
              </Tag>
            </div>
            <p className={styles.marketDrawerDesc}>
              {descOf(selected, lang) || t("experts.noMarketDescription")}
            </p>
            {selected.skill_slugs && selected.skill_slugs.length > 0 && (
              <div>
                <div className={styles.marketSectionTitle}>
                  {t("experts.marketIncludedSkills")}
                </div>
                <div className={styles.marketSkillList}>
                  {selected.skill_slugs.map((slug) => (
                    <Tag key={slug}>{slug}</Tag>
                  ))}
                </div>
              </div>
            )}
            <div>
              <div className={styles.marketSectionTitle}>
                {t("experts.marketWorkflowPrompt")}
              </div>
              <div className={styles.marketWorkflowPreview}>
                {detailLoading ? (
                  <Spin size="small" />
                ) : (
                  selected.content?.[lang] ||
                  selected.content?.zh ||
                  t("experts.marketWorkflowEmpty")
                )}
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
