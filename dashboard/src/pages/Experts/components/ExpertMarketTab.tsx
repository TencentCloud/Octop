import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Button, Drawer, Input, Result, Spin, Tag } from "antd";
import { message } from "@/utils/antdMessage";

import {
  CheckCircle,
  Download,
  Layers,
  RefreshCw,
  Search,
  Zap,
} from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  expertMarketApi,
  type ExpertMarketQuickPrompt,
  type MarketExpert,
} from "../../../api/modules/expertMarket";
import type { PublishedExpert } from "../../../api/modules/publishedExperts";
import { PublishedExpertCard } from "./PublishedExpertCard";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import { FadeInImg } from "../../../components/FadeInImg";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import { apiErrorMessage } from "../../../utils/apiError";
import { isCatalogNetworkError } from "../../../utils/networkError";
import { pickLocale } from "../../../utils/localizedText";
import { pastelIconBackground } from "../../../utils/pastelIconBackground";
import {
  parseWorkflowFrontmatterMeta,
  splitMarkdownFrontmatter,
} from "../../../utils/markdown";
import { iconForName } from "./iconForName";
import styles from "../index.module.less";

interface ExpertMarketTabProps {
  lang: "zh" | "en";
  installedExpertIds: Set<string>;
  onRequestCreate: (expert: MarketExpert) => void;
  publishedExperts: PublishedExpert[];
  publishedLoading: boolean;
  canManagePublished: (expert: PublishedExpert) => boolean;
  onInstallPublished: (expert: PublishedExpert) => void;
  onPublishedChanged: () => void;
}

const SCENE_ALL = "";

function descOf(expert: MarketExpert, lang: "zh" | "en"): string {
  return pickLocale(expert.description, lang) || "";
}

function labelOf(expert: MarketExpert, lang: "zh" | "en"): string {
  return pickLocale(expert.label, lang) || expert.slug;
}

function sceneLabel(scene: string, t: TFunction): string {
  if (!scene) return t("experts.sceneAll", "全部");
  return t(`experts.scenes.${scene}`, { defaultValue: scene });
}

function promptText(
  prompt: ExpertMarketQuickPrompt,
  lang: "zh" | "en",
  field: "title" | "description",
): string {
  return pickLocale(prompt[field], lang) || "";
}

function taskExampleTexts(expert: MarketExpert, lang: "zh" | "en"): string[] {
  const raw = expert.task_examples;
  if (!raw) return [];
  const primary = lang === "zh" ? raw.zh : raw.en;
  const fallback = lang === "zh" ? raw.en : raw.zh;
  const picked = primary?.length ? primary : fallback;
  return (picked ?? []).map((item) => item.trim()).filter(Boolean);
}

export default function ExpertMarketTab({
  lang,
  installedExpertIds,
  onRequestCreate,
  publishedExperts,
  publishedLoading,
  canManagePublished,
  onInstallPublished,
  onPublishedChanged,
}: ExpertMarketTabProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<MarketExpert[]>([]);
  const [scenes, setScenes] = useState<string[]>([]);
  const [activeScene, setActiveScene] = useState(SCENE_ALL);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [networkFailure, setNetworkFailure] = useState(false);
  const itemsRef = useRef(items);
  const [selected, setSelected] = useState<MarketExpert | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  itemsRef.current = items;

  const fetchMarket = useCallback(
    async (query = keyword, force = false) => {
      if (force) setRefreshing(true);
      else setLoading(true);
      try {
        const resp = await expertMarketApi.list(query);
        setItems(resp?.items ?? []);
        if (Array.isArray(resp?.scenes) && resp.scenes.length > 0) {
          setScenes(resp.scenes);
        }
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
              : t("experts.marketUnavailable"),
          );
        }
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

  const openDetail = useCallback(
    async (expert: MarketExpert) => {
      setSelected(expert);
      setDetailLoading(true);
      try {
        const detail = await expertMarketApi.get(expert.slug);
        setSelected(detail);
      } catch (err) {
        message.error(
          apiErrorMessage(err, t("experts.marketDetailLoadFailed"), t),
        );
      } finally {
        setDetailLoading(false);
      }
    },
    [t],
  );

  const openCreate = useCallback(
    (expert: MarketExpert) => {
      setSelected(null);
      onRequestCreate(expert);
    },
    [onRequestCreate],
  );

  const selectedTaskExamples = selected ? taskExampleTexts(selected, lang) : [];

  const visibleItems = useMemo(() => {
    if (keyword.trim() || !activeScene) return items;
    const scene = activeScene.toLowerCase();
    return items.filter((item) => (item.scene || "").toLowerCase() === scene);
  }, [activeScene, items, keyword]);

  const visiblePublished = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    if (!query) return publishedExperts;
    return publishedExperts.filter((expert) =>
      [expert.name, expert.description, expert.creator_username].some((part) =>
        (part ?? "").toLowerCase().includes(query),
      ),
    );
  }, [keyword, publishedExperts]);

  const totalText = useMemo(
    () => t("experts.totalMarket", { count: visibleItems.length }),
    [t, visibleItems.length],
  );

  const sceneOptions = useMemo(
    () => [
      { value: SCENE_ALL, label: sceneLabel(SCENE_ALL, t) },
      ...scenes.map((scene) => ({
        value: scene,
        label: sceneLabel(scene, t),
      })),
    ],
    [scenes, t],
  );

  const workflowDoc = useMemo(() => {
    const raw =
      selected?.content?.[lang] ||
      selected?.content?.zh ||
      selected?.content?.en ||
      "";
    if (!raw.trim()) {
      return {
        body: "",
        meta: parseWorkflowFrontmatterMeta(null),
      };
    }
    const split = splitMarkdownFrontmatter(raw);
    return {
      body: split.body,
      meta: parseWorkflowFrontmatterMeta(split.raw),
    };
  }, [lang, selected]);

  const catalogFailed = loadFailed && items.length === 0;
  const marketLoading = loading && items.length === 0;
  const publishedSection =
    visiblePublished.length > 0 ? (
      <div className={styles.marketBlock}>
        <div className={styles.marketBlockTitle}>
          {t("experts.published.listTitle", {
            count: visiblePublished.length,
          })}
        </div>
        <p className={styles.marketBlockHint}>
          {t("experts.published.listHint")}
        </p>
        <div className={styles.cardGrid}>
          {visiblePublished.map((expert) => (
            <PublishedExpertCard
              key={expert.id}
              expert={expert}
              canManage={canManagePublished(expert)}
              onInstall={onInstallPublished}
              onChanged={onPublishedChanged}
            />
          ))}
        </div>
      </div>
    ) : !publishedLoading &&
      !marketLoading &&
      !catalogFailed &&
      !keyword.trim() &&
      publishedExperts.length === 0 ? (
      <div className={styles.marketBlock}>
        <div className={styles.marketBlockTitle}>
          {t("experts.published.listTitle", { count: 0 })}
        </div>
        <p className={styles.marketBlockHint}>
          {t("experts.published.emptyHint")}
        </p>
      </div>
    ) : null;

  const showPublished =
    catalogFailed || !activeScene || Boolean(keyword.trim());

  const scenePills =
    !catalogFailed && !marketLoading && !keyword && sceneOptions.length > 1 ? (
      <div className={styles.marketSceneTabsWrap}>
        {sceneOptions.map((opt) => {
          const active = activeScene === opt.value;
          return (
            <button
              key={opt.value || SCENE_ALL}
              type="button"
              aria-pressed={active}
              className={
                active
                  ? `${styles.marketScenePill} ${styles.marketScenePillActive}`
                  : styles.marketScenePill
              }
              onClick={() => setActiveScene(opt.value)}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    ) : null;

  return (
    <div className={styles.marketContainer}>
      {!catalogFailed && !marketLoading && (
        <div className={styles.gridToolbar}>
          <div
            className={`${styles.gridToolbarRight} ${styles.marketToolbarRight}`}
          >
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
              onClick={() => {
                onPublishedChanged();
                void fetchMarket(keyword, true);
              }}
              type="button"
            >
              <RefreshCw
                size={14}
                className={refreshing ? styles.spinning : undefined}
              />
            </button>
          </div>
        </div>
      )}

      {showPublished ? publishedSection : null}

      {!catalogFailed && !marketLoading && (
        <div
          className={
            showPublished && publishedSection
              ? `${styles.marketBlockTitle} ${styles.marketCatalogTitle}`
              : styles.marketBlockTitle
          }
        >
          {totalText}
        </div>
      )}

      {scenePills}

      {marketLoading ? (
        <div className={styles.marketStage}>
          <Spin />
        </div>
      ) : catalogFailed ? (
        <div className={styles.marketStage}>
          <Result
            className={styles.marketLoadResult}
            icon={<OctopEmptyMascot size={120} />}
            title={t("experts.marketLoadFailed")}
            subTitle={
              networkFailure
                ? t("apiErrors.NETWORK_ERROR")
                : t("experts.marketUnavailable")
            }
            extra={
              <Button
                type="primary"
                loading={refreshing}
                onClick={() => {
                  onPublishedChanged();
                  void fetchMarket(keyword, true);
                }}
              >
                {t("common.retry")}
              </Button>
            }
          />
        </div>
      ) : visibleItems.length === 0 ? (
        <div className={styles.emptyState}>
          <Layers size={48} style={{ color: "var(--fn-text-tertiary)" }} />
          <div className={styles.emptyTitle}>{t("experts.emptyMarket")}</div>
          <div className={styles.emptyHint}>{t("experts.emptyMarketHint")}</div>
        </div>
      ) : (
        <div className={styles.cardGrid}>
          {visibleItems.map((expert) => {
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
                <div className={styles.marketCardHeader}>
                  <div
                    className={styles.agentCardIcon}
                    style={{
                      color: accent,
                      background: `${accent}18`,
                    }}
                  >
                    {expert.icon_url ? (
                      <FadeInImg
                        src={expert.icon_url}
                        alt=""
                        crossOrigin="anonymous"
                        className={styles.marketIconImg}
                      />
                    ) : (
                      iconForName(expert.icon_name || "zap", 20)
                    )}
                  </div>
                  <div className={styles.agentCardTitleBlock}>
                    <div className={styles.agentCardName}>{label}</div>
                  </div>
                </div>
                <div className={styles.agentCardDesc}>
                  {desc || t("experts.noMarketDescription")}
                </div>
                <div className={styles.marketCardFooter}>
                  <div className={styles.marketCardFooterStart}>
                    <span className={styles.marketMeta}>
                      <Zap size={13} />
                      {t("experts.marketSkillCount", {
                        count:
                          expert.skill_count ?? expert.skill_slugs?.length ?? 0,
                      })}
                    </span>
                    {installed && (
                      <div className={styles.expertInstalledLabel}>
                        <CheckCircle size={12} />
                        {t("experts.installedBadge")}
                      </div>
                    )}
                  </div>
                  <Button
                    size="small"
                    type="primary"
                    icon={<Download size={14} />}
                    onClick={(e) => {
                      e.stopPropagation();
                      openCreate(expert);
                    }}
                  >
                    {installed
                      ? t("experts.createAgainFromMarket")
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
        destroyOnHidden
        onClose={() => setSelected(null)}
        title={selected ? labelOf(selected, lang) : ""}
        footer={
          selected ? (
            <Button
              type="primary"
              size="large"
              block
              icon={<Download size={14} />}
              onClick={() => openCreate(selected)}
            >
              {installedExpertIds.has(selected.id)
                ? t("experts.createAgainFromMarket")
                : t("experts.createFromMarket")}
            </Button>
          ) : null
        }
      >
        {selected && (
          <div className={styles.marketDrawerBody}>
            <p className={styles.marketDrawerDesc}>
              {descOf(selected, lang) || t("experts.noMarketDescription")}
            </p>
            <div>
              <div className={styles.marketSectionTitle}>
                {t("experts.marketQuickPrompts")}
              </div>
              {detailLoading ? (
                <Spin size="small" />
              ) : selected.quick_prompts &&
                selected.quick_prompts.length > 0 ? (
                <div className={styles.marketQuickPromptList}>
                  {selected.quick_prompts.map((card, idx) => (
                    <div
                      key={`${promptText(card, lang, "title")}-${idx}`}
                      className={styles.marketQuickPromptCard}
                    >
                      <div
                        className={styles.marketQuickPromptIcon}
                        style={{
                          background: pastelIconBackground(card.color, idx),
                        }}
                      >
                        {iconForName(card.icon_name || "zap", 16)}
                      </div>
                      <div>
                        <div className={styles.marketQuickPromptTitle}>
                          {promptText(card, lang, "title")}
                        </div>
                        <div className={styles.marketQuickPromptDesc}>
                          {promptText(card, lang, "description")}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className={styles.marketWorkflowPreview}>
                  {t("experts.marketQuickPromptsEmpty")}
                </div>
              )}
            </div>
            <div>
              <div className={styles.marketSectionTitle}>
                {t("experts.marketTaskExamples")}
              </div>
              {detailLoading ? (
                <Spin size="small" />
              ) : selectedTaskExamples.length > 0 ? (
                <div className={styles.marketTaskExampleList}>
                  {selectedTaskExamples.map((text, idx) => (
                    <div
                      key={`${text}-${idx}`}
                      className={styles.marketTaskExampleItem}
                      title={text}
                    >
                      {text}
                    </div>
                  ))}
                </div>
              ) : (
                <div className={styles.marketWorkflowEmpty}>
                  {t("experts.marketTaskExamplesEmpty")}
                </div>
              )}
            </div>
            <div>
              <div className={styles.marketSectionTitle}>
                {t("experts.marketWorkflowPrompt")}
              </div>
              {detailLoading ? (
                <div className={styles.marketWorkflowPreview}>
                  <Spin size="small" />
                </div>
              ) : workflowDoc.body ||
                workflowDoc.meta.version ||
                workflowDoc.meta.children.length > 0 ? (
                <div className={styles.marketWorkflowPanel}>
                  {(workflowDoc.meta.displayName ||
                    workflowDoc.meta.version ||
                    workflowDoc.meta.packageType ||
                    workflowDoc.meta.children.length > 0) && (
                    <div className={styles.marketWorkflowMeta}>
                      <div className={styles.marketWorkflowMetaTitle}>
                        {t("experts.marketWorkflowMeta")}
                      </div>
                      <div className={styles.marketTagRow}>
                        {workflowDoc.meta.displayName && (
                          <Tag bordered={false}>
                            {workflowDoc.meta.displayName}
                          </Tag>
                        )}
                        {workflowDoc.meta.version && (
                          <Tag bordered={false}>
                            {t("experts.marketWorkflowVersion", {
                              version: workflowDoc.meta.version,
                            })}
                          </Tag>
                        )}
                        {workflowDoc.meta.packageType && (
                          <Tag bordered={false}>
                            {workflowDoc.meta.packageType}
                          </Tag>
                        )}
                      </div>
                      {workflowDoc.meta.children.length > 0 && (
                        <div className={styles.marketWorkflowChildren}>
                          <div className={styles.marketWorkflowChildrenLabel}>
                            {t("experts.marketWorkflowChildren")}
                          </div>
                          <div className={styles.marketSkillList}>
                            {workflowDoc.meta.children.map((slug) => (
                              <Tag key={slug}>{slug}</Tag>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {workflowDoc.body ? (
                    <div className={styles.marketWorkflowPreview}>
                      <Markdown
                        content={workflowDoc.body}
                        className={styles.marketWorkflowMarkdown}
                      />
                    </div>
                  ) : (
                    <div className={styles.marketWorkflowPreview}>
                      <span className={styles.marketWorkflowEmpty}>
                        {t("experts.marketWorkflowEmpty")}
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <div className={styles.marketWorkflowPreview}>
                  <span className={styles.marketWorkflowEmpty}>
                    {t("experts.marketWorkflowEmpty")}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
