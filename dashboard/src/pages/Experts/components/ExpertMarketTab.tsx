import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Button, Drawer, Input, message, Segmented, Spin, Tag } from "antd";
import {
  CircleCheck,
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
import Markdown from "../../../components/Markdown/LazyMarkdown";
import { apiErrorMessage } from "../../../utils/apiError";
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
  onCreated: (agentId: string) => void;
}

const SCENE_ALL = "";

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

export default function ExpertMarketTab({
  lang,
  installedExpertIds,
  onCreated,
}: ExpertMarketTabProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<MarketExpert[]>([]);
  const [scenes, setScenes] = useState<string[]>([]);
  const [activeScene, setActiveScene] = useState(SCENE_ALL);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<MarketExpert | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [creatingSlug, setCreatingSlug] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchMarket = useCallback(
    async (query = keyword, scene = activeScene, force = false) => {
      if (force) setRefreshing(true);
      else setLoading(true);
      try {
        const resp = await expertMarketApi.list(query, scene);
        setItems(resp?.items ?? []);
        if (Array.isArray(resp?.scenes) && resp.scenes.length > 0) {
          setScenes(resp.scenes);
        }
        setErrorMessage(null);
      } catch (err) {
        const msg = marketErrorMessage(err, t("experts.marketBackendMissing"));
        setErrorMessage(msg);
        message.error(msg);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [activeScene, keyword, t],
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const scene = keyword.trim() ? SCENE_ALL : activeScene;
      void fetchMarket(keyword, scene);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [keyword, activeScene, fetchMarket]);

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

  const createMarketExpert = useCallback(
    async (expert: MarketExpert) => {
      if (creatingSlug) return;
      setCreatingSlug(expert.slug);
      try {
        const result = await expertMarketApi.install(expert.slug);
        const enrichment = result.market?.welcome_enrichment;
        if (enrichment === "pending") {
          message.success(
            t("experts.marketCreateSuccessEnriching", { name: result.name }),
          );
        } else {
          message.success(
            t("experts.marketCreateSuccess", { name: result.name }),
          );
        }
        setSelected(null);
        onCreated(result.agent_id);
      } catch (err) {
        message.error(apiErrorMessage(err, t("experts.createFailed"), t));
      } finally {
        setCreatingSlug(null);
      }
    },
    [creatingSlug, onCreated, t],
  );

  const totalText = useMemo(
    () => t("experts.totalMarket", { count: items.length }),
    [items.length, t],
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
            onClick={() => void fetchMarket(keyword, activeScene, true)}
            type="button"
          >
            <RefreshCw
              size={14}
              className={refreshing ? styles.spinning : undefined}
            />
          </button>
        </div>
      </div>

      {!keyword && sceneOptions.length > 1 && (
        <div className={styles.marketSceneTabsWrap}>
          <Segmented
            block
            size="large"
            value={activeScene}
            onChange={(v) => setActiveScene(String(v))}
            options={sceneOptions}
            className={styles.marketSceneTabs}
          />
        </div>
      )}

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
                onClick={() => void fetchMarket(keyword, activeScene, true)}
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
                <div className={styles.marketCardHeader}>
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
                    type="primary"
                    icon={<Download size={14} />}
                    loading={creatingSlug === expert.slug}
                    disabled={Boolean(creatingSlug)}
                    onClick={(e) => {
                      e.stopPropagation();
                      void createMarketExpert(expert);
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
              disabled={Boolean(creatingSlug)}
              onClick={() => void createMarketExpert(selected)}
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
