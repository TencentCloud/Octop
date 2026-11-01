import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Button, Drawer, Input, Result, Spin, Tag } from "antd";
import { message } from "@/utils/antdMessage";

import {
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  Layers,
  RefreshCw,
  Search,
  Zap,
} from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import {
  expertMarketApi,
  type ExpertMarketQuickPrompt,
  type MarketExpert,
} from "../../../api/modules/expertMarket";
import type { PublishedExpert } from "../../../api/modules/publishedExperts";
import { PublishedExpertCard } from "./PublishedExpertCard";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import { FadeInImg } from "../../../components/FadeInImg";
import { CardSkeleton } from "../../../components/Skeleton";
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
  onInstallPublished: (expert: PublishedExpert) => void;
  onPublishedChanged: () => void;
}

const SCENE_ALL = "";
const SOURCE_REMOTE = "remote";
const SOURCE_PUBLISHED = "published";

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

function SceneScrollArrow({
  show,
  side,
  label,
  onClick,
}: {
  show: boolean;
  side: "prev" | "next";
  label: string;
  onClick: () => void;
}) {
  return (
    <AnimatePresence initial={false}>
      {show ? (
        <motion.button
          key={side}
          type="button"
          className={`${styles.marketSceneArrow} ${
            side === "prev"
              ? styles.marketSceneArrowPrev
              : styles.marketSceneArrowNext
          }`}
          aria-label={label}
          initial={false}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={onClick}
        >
          <span className={styles.marketSceneArrowIcon}>
            {side === "prev" ? (
              <ChevronLeft size={14} />
            ) : (
              <ChevronRight size={14} />
            )}
          </span>
        </motion.button>
      ) : null}
    </AnimatePresence>
  );
}

function MarketSceneTabs({
  options,
  active,
  onSelect,
  prevLabel,
  nextLabel,
}: {
  options: Array<{ value: string; label: string }>;
  active: string;
  onSelect: (value: string) => void;
  prevLabel: string;
  nextLabel: string;
}) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef({
    pointerId: -1,
    startX: 0,
    startScroll: 0,
    moved: false,
  });
  const [edges, setEdges] = useState({ left: false, right: false });

  const updateEdges = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    const left = el.scrollLeft > 2;
    const right = max - el.scrollLeft > 2;
    setEdges((prev) =>
      prev.left === left && prev.right === right ? prev : { left, right },
    );
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    updateEdges();
    el.addEventListener("scroll", updateEdges, { passive: true });
    const observer = new ResizeObserver(updateEdges);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", updateEdges);
      observer.disconnect();
    };
  }, [options, updateEdges]);

  const scrollByDir = (dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({
      left: dir * Math.max(160, Math.round(el.clientWidth * 0.7)),
      behavior: "smooth",
    });
  };

  return (
    <div className={styles.marketSceneScroller}>
      <SceneScrollArrow
        show={edges.left}
        side="prev"
        label={prevLabel}
        onClick={() => scrollByDir(-1)}
      />
      <div
        ref={scrollerRef}
        className={styles.marketSceneTabsWrap}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          const el = scrollerRef.current;
          if (!el || el.scrollWidth <= el.clientWidth + 1) return;
          // Capture only after the pointer actually drags. Capturing on
          // pointerdown retargets the click away from the pill.
          dragRef.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startScroll: el.scrollLeft,
            moved: false,
          };
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current;
          if (drag.pointerId !== event.pointerId) return;
          const el = scrollerRef.current;
          if (!el) return;
          const dx = event.clientX - drag.startX;
          if (!drag.moved) {
            if (Math.abs(dx) <= 6) return;
            drag.moved = true;
            el.setPointerCapture(event.pointerId);
          }
          el.scrollLeft = drag.startScroll - dx;
        }}
        onPointerUp={(event) => {
          if (dragRef.current.pointerId !== event.pointerId) return;
          dragRef.current.pointerId = -1;
        }}
        onPointerCancel={() => {
          dragRef.current.pointerId = -1;
          dragRef.current.moved = false;
        }}
        onClickCapture={(event) => {
          if (!dragRef.current.moved) return;
          dragRef.current.moved = false;
          event.preventDefault();
          event.stopPropagation();
        }}
      >
        {options.map((opt) => {
          const selected = active === opt.value;
          return (
            <button
              key={opt.value || SCENE_ALL}
              type="button"
              aria-pressed={selected}
              className={
                selected
                  ? `${styles.marketScenePill} ${styles.marketScenePillActive}`
                  : styles.marketScenePill
              }
              onClick={() => onSelect(opt.value)}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <SceneScrollArrow
        show={edges.right}
        side="next"
        label={nextLabel}
        onClick={() => scrollByDir(1)}
      />
    </div>
  );
}

export default function ExpertMarketTab({
  lang,
  installedExpertIds,
  onRequestCreate,
  publishedExperts,
  publishedLoading,
  onInstallPublished,
  onPublishedChanged,
}: ExpertMarketTabProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<MarketExpert[]>([]);
  const [scenes, setScenes] = useState<string[]>([]);
  const [activeScene, setActiveScene] = useState(SCENE_ALL);
  const [source, setSource] = useState<
    typeof SOURCE_REMOTE | typeof SOURCE_PUBLISHED
  >(SOURCE_REMOTE);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [networkFailure, setNetworkFailure] = useState(false);
  const [listQuery, setListQuery] = useState<string | null>(null);
  const listQueryRef = useRef<string | null>(null);
  const reqGen = useRef(0);
  const [selected, setSelected] = useState<MarketExpert | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchMarket = useCallback(
    async (query: string, gen: number, force = false) => {
      if (gen !== reqGen.current) return;
      const trimmed = query.trim();
      if (force) setRefreshing(true);
      else if (listQueryRef.current === null) setLoading(true);
      try {
        const resp = await expertMarketApi.list(trimmed);
        if (gen !== reqGen.current) return;
        setItems(resp?.items ?? []);
        if (Array.isArray(resp?.scenes) && resp.scenes.length > 0) {
          setScenes(resp.scenes);
        }
        listQueryRef.current = trimmed;
        setListQuery(trimmed);
        setLoadFailed(false);
        setNetworkFailure(false);
      } catch (err) {
        if (gen !== reqGen.current) return;
        const network = isCatalogNetworkError(err, "NETWORK_ERROR");
        setNetworkFailure(network);
        if (listQueryRef.current === null) {
          setLoadFailed(true);
        } else {
          listQueryRef.current = trimmed;
          setListQuery(trimmed);
          message.error(
            network
              ? t("apiErrors.NETWORK_ERROR")
              : t("experts.marketUnavailable"),
          );
        }
      } finally {
        if (gen === reqGen.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [t],
  );

  useEffect(() => {
    const gen = ++reqGen.current;
    const query = keyword;
    const timer = setTimeout(() => {
      void fetchMarket(query, gen);
    }, 300);
    return () => clearTimeout(timer);
  }, [keyword, fetchMarket]);

  const reloadMarket = useCallback(() => {
    const gen = ++reqGen.current;
    void fetchMarket(keyword, gen, true);
  }, [fetchMarket, keyword]);

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
    const queryText = keyword.trim();
    if ((queryText && listQuery === queryText) || !activeScene) return items;
    const scene = activeScene.toLowerCase();
    return items.filter((item) => (item.scene || "").toLowerCase() === scene);
  }, [activeScene, items, keyword, listQuery]);

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

  const queryText = keyword.trim();
  const catalogReady = listQuery !== null;
  const catalogFailed = loadFailed && !catalogReady;
  const initialLoading = loading && !catalogReady;
  const marketAwaiting = catalogReady && listQuery !== queryText;
  const visiblePublished = useMemo(() => {
    const query = queryText.toLowerCase();
    if (!query) return publishedExperts;
    return publishedExperts.filter((expert) =>
      [expert.name, expert.description, expert.creator_username].some((part) =>
        (part ?? "").toLowerCase().includes(query),
      ),
    );
  }, [publishedExperts, queryText]);
  const publishedOnly = source === SOURCE_PUBLISHED;
  const publishedCards =
    visiblePublished.length > 0 ? (
      <div className={styles.cardGrid}>
        {visiblePublished.map((expert) => (
          <PublishedExpertCard
            key={expert.id}
            expert={expert}
            onInstall={onInstallPublished}
          />
        ))}
      </div>
    ) : null;
  const showSceneTabs =
    source === SOURCE_REMOTE &&
    !catalogFailed &&
    catalogReady &&
    !marketAwaiting &&
    !queryText &&
    sceneOptions.length > 1;

  return (
    <div className={styles.marketContainer}>
      {!initialLoading && (
        <div className={`${styles.gridToolbar} ${styles.marketSourceRow}`}>
          <div className={styles.marketSourceTabs} role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={source === SOURCE_PUBLISHED}
              className={
                source === SOURCE_PUBLISHED
                  ? `${styles.marketSourceTab} ${styles.marketSourceTabActive}`
                  : styles.marketSourceTab
              }
              onClick={() => setSource(SOURCE_PUBLISHED)}
            >
              {t("experts.published.scene")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={source === SOURCE_REMOTE}
              className={
                source === SOURCE_REMOTE
                  ? `${styles.marketSourceTab} ${styles.marketSourceTabActive}`
                  : styles.marketSourceTab
              }
              onClick={() => setSource(SOURCE_REMOTE)}
            >
              {t("experts.marketSourceRemote")}
            </button>
          </div>
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
                reloadMarket();
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

      {showSceneTabs ? (
        <MarketSceneTabs
          options={sceneOptions}
          active={activeScene}
          onSelect={setActiveScene}
          prevLabel={t("experts.marketScenePrev")}
          nextLabel={t("experts.marketSceneNext")}
        />
      ) : null}

      {initialLoading ? (
        <div className={styles.marketStage}>
          <Spin />
        </div>
      ) : publishedOnly ? (
        publishedCards ?? (
          <div className={styles.emptyState}>
            <div className={styles.emptyHint}>
              {publishedLoading
                ? null
                : queryText
                ? t("experts.filterEmpty")
                : t("experts.published.emptyHint")}
            </div>
          </div>
        )
      ) : catalogFailed ? (
        <>
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
                    reloadMarket();
                  }}
                >
                  {t("common.retry")}
                </Button>
              }
            />
          </div>
        </>
      ) : (
        <>
          {marketAwaiting ? (
            <div className={styles.loadingSkeleton}>
              <CardSkeleton
                count={6}
                containerStyle={{
                  gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                  rowGap: 16,
                  columnGap: 12,
                  padding: "20px 0 24px",
                }}
              />
            </div>
          ) : visibleItems.length === 0 ? (
            <div className={styles.emptyState}>
              <Layers size={48} style={{ color: "var(--fn-text-tertiary)" }} />
              <div className={styles.emptyTitle}>
                {t("experts.emptyMarket")}
              </div>
              <div className={styles.emptyHint}>
                {t("experts.emptyMarketHint")}
              </div>
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
                              expert.skill_count ??
                              expert.skill_slugs?.length ??
                              0,
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
        </>
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
