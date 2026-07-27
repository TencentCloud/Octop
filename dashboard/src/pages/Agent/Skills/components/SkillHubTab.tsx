// dashboard/src/pages/Agent/Skills/components/SkillHubTab.tsx
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { Button, Input, message, Spin, Tag, Segmented } from "antd";
import { CircleCheck, Download, Link, RefreshCw, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../../api/request";
import { apiErrorMessage } from "../../../../utils/apiError";
import { SkillHubDetailDrawer } from "./SkillHubDetailDrawer";
import type { SkillHubSkill } from "./SkillHubDetailDrawer";
import { loadRankingsCache, saveRankingsCache } from "./skillHubCache";
import styles from "../index.module.less";

interface SkillHubTabProps {
  /** The currently active agent (used as default in picker). */
  activeAgentId: string | null;
}

type RankingType = "recommended" | "trending" | "hot" | "newest";

const RANKING_TABS: { key: RankingType; labelKey: string }[] = [
  { key: "recommended", labelKey: "skills.rankingRecommended" },
  { key: "trending", labelKey: "skills.rankingTrending" },
  { key: "hot", labelKey: "skills.rankingHot" },
  { key: "newest", labelKey: "skills.rankingNewest" },
];

interface RankingsResponse {
  rankings?: Record<string, { section?: string; skills?: SkillHubSkill[] }>;
  errors?: Record<string, string>;
}

function requiresApiKey(skill: SkillHubSkill): boolean {
  const v = skill.labels?.["requires_api_key"];
  return v === true || v === "true";
}

function skillDesc(skill: SkillHubSkill): string {
  return skill.description_zh || skill.description || "";
}

export default function SkillHubTab({ activeAgentId }: SkillHubTabProps) {
  const { t } = useTranslation();
  const [hubSkills, setHubSkills] = useState<SkillHubSkill[]>([]);
  const [rankings, setRankings] = useState<Record<string, SkillHubSkill[]>>(
    () => loadRankingsCache() ?? {},
  );
  const [activeRanking, setActiveRanking] =
    useState<RankingType>("recommended");
  // If we already have cached data, start in non-loading state.
  const [loading, setLoading] = useState(
    () => Object.keys(loadRankingsCache() ?? {}).length === 0,
  );
  const [searching, setSearching] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<SkillHubSkill | null>(
    null,
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [installingSlug, setInstallingSlug] = useState<string | null>(null);
  const [installedSlugs, setInstalledSlugs] = useState<Set<string>>(new Set());
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Fetch all ranking sections in one call; tab switching is then local.
  // Skips the network request when a fresh cache entry exists.
  const fetchRankings = useCallback(
    async (force = false) => {
      if (!force) {
        const cached = loadRankingsCache();
        if (cached && Object.keys(cached).length > 0) {
          setRankings(cached);
          setLoading(false);
          return;
        }
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      setLoadError(null);
      try {
        const agentId = activeAgentId ?? "_";
        const resp = await request<RankingsResponse>(
          `/agents/${agentId}/skills/hub/rankings?type=all`,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          const sections = resp?.rankings ?? {};
          const map: Record<string, SkillHubSkill[]> = {};
          for (const key of Object.keys(sections)) {
            map[key] = sections[key]?.skills ?? [];
          }
          setRankings(map);
          // Do not cache a partial response for a full day, so a later visit
          // can retry after the transient upstream failure has recovered.
          if (Object.keys(resp?.errors ?? {}).length === 0) {
            saveRankingsCache(map);
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setLoadError(
            err instanceof Error
              ? err.message
              : "Failed to load SkillHub rankings",
          );
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    },
    [activeAgentId],
  );

  const fetchHubSkills = useCallback(
    async (query: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setSearching(true);
      setLoadError(null);
      try {
        const agentId = activeAgentId ?? "_";
        const results = await request<SkillHubSkill[]>(
          `/agents/${agentId}/skills/hub/search?q=${encodeURIComponent(
            query,
          )}&limit=50`,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) setHubSkills(results ?? []);
      } catch (err) {
        if (!controller.signal.aborted) {
          setLoadError(
            err instanceof Error ? err.message : "Failed to search SkillHub",
          );
        }
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    },
    [activeAgentId],
  );

  // Empty keyword -> rankings (immediate). Non-empty -> debounced search.
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!searchKeyword) {
      void fetchRankings();
      return;
    }
    debounceTimer.current = setTimeout(() => {
      void fetchHubSkills(searchKeyword.trim());
    }, 350);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [searchKeyword, fetchRankings, fetchHubSkills]);

  // Seed installed slugs from agent's existing skills
  useEffect(() => {
    if (!activeAgentId) return;
    request<Array<{ name: string; slug?: string }>>(
      `/agents/${activeAgentId}/skills`,
    )
      .then((rows) =>
        setInstalledSlugs(new Set((rows ?? []).map((r) => r.slug ?? r.name))),
      )
      .catch(() => {
        // non-critical: installed indicators may be stale
      });
  }, [activeAgentId]);

  const isInstalled = useCallback(
    (slug: string) => installedSlugs.has(slug),
    [installedSlugs],
  );

  const handleInstall = useCallback(
    async (skill: SkillHubSkill) => {
      // Allow re-install: an installed skill can be re-downloaded (the backend
      // overwrites), so a user who edited / disabled / deleted it can always
      // restore it from the marketplace. Only block while a request is in
      // flight.
      if (installingSlug) return;
      if (!activeAgentId) {
        message.warning(t("skills.noAgentSelected"));
        return;
      }
      setDrawerOpen(false);
      setInstallingSlug(skill.slug);
      try {
        const result = await request<{
          installed: boolean;
          name: string;
          enabled: boolean;
        }>(`/agents/${activeAgentId}/skills/hub/install`, {
          method: "POST",
          body: JSON.stringify({
            skill_name: skill.slug,
            enable: true,
            display_name: skill.name,
            icon_url: skill.iconUrl ?? null,
          }),
        });
        if (result?.installed) {
          message.success(t("skills.installSuccess"));
          setInstalledSlugs((prev) => new Set([...prev, skill.slug]));
        } else {
          message.error(t("skills.installFailed"));
        }
      } catch (err) {
        message.error(apiErrorMessage(err, t("skills.installFailed"), t));
      } finally {
        setInstallingSlug(null);
      }
    },
    [activeAgentId, installingSlug, t],
  );

  const displaySkills = useMemo(() => {
    const base = searchKeyword ? hubSkills : rankings[activeRanking] ?? [];
    return base.slice().sort((a, b) => {
      const ai = isInstalled(a.slug) ? 0 : 1;
      const bi = isInstalled(b.slug) ? 0 : 1;
      return ai - bi;
    });
  }, [searchKeyword, hubSkills, rankings, activeRanking, isInstalled]);

  const handleCardClick = (skill: SkillHubSkill) => {
    setSelectedSkill(skill);
    setDrawerOpen(true);
  };

  if (loading && !searchKeyword) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: 200,
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          minHeight: 200,
          gap: 16,
          paddingTop: 48,
        }}
      >
        <div style={{ color: "var(--fn-color-danger, #ff4d4f)" }}>
          {loadError}
        </div>
        <Button
          icon={<RefreshCw size={14} />}
          onClick={() => void fetchRankings(true)}
        >
          {t("common.refresh")}
        </Button>
      </div>
    );
  }

  return (
    <div className={styles.skillHubContainer}>
      {/* Toolbar */}
      <div className={styles.skillHubToolbar}>
        <Input
          className={styles.skillHubSearch}
          placeholder={t("skills.searchSkillHub")}
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          allowClear
          suffix={searching ? <Spin size="small" /> : undefined}
        />
        <Button
          icon={<Link size={14} />}
          href="https://skillhub.tencent.com/"
          target="_blank"
          type="text"
          size="small"
          style={{ color: "var(--fn-text-tertiary)" }}
        >
          SkillHub
        </Button>
        <Button
          icon={<RefreshCw size={14} />}
          type="text"
          size="small"
          style={{ color: "var(--fn-text-tertiary)" }}
          onClick={() => void fetchRankings(true)}
        >
          {t("common.refresh")}
        </Button>
      </div>

      {/* Ranking tabs — full-width segmented control, equal quarters (browse mode) */}
      {!searchKeyword && (
        <Segmented
          block
          size="large"
          value={activeRanking}
          onChange={(v) => setActiveRanking(v as RankingType)}
          options={RANKING_TABS.map(({ key, labelKey }) => ({
            value: key,
            label: t(labelKey),
          }))}
          className={styles.rankingTabs}
        />
      )}

      {/* Grid */}
      {displaySkills.length === 0 ? (
        <div
          style={{
            color: "var(--fn-text-tertiary)",
            textAlign: "center",
            padding: "40px 0",
          }}
        >
          {t("skills.rankingsEmpty")}
        </div>
      ) : (
        <div className={styles.hubGrid}>
          {displaySkills.map((skill) => (
            <div
              key={skill.slug}
              className={styles.hubCard}
              onClick={() => handleCardClick(skill)}
            >
              <div className={styles.hubCardHeader}>
                {skill.iconUrl ? (
                  <img
                    src={skill.iconUrl}
                    alt=""
                    className={styles.hubCardIcon}
                  />
                ) : (
                  <span className={styles.hubCardIconFallback}>
                    <Zap size={16} fill="currentColor" />
                  </span>
                )}
                <span className={styles.hubCardName}>{skill.name}</span>
                {skill.verified && (
                  <CircleCheck
                    size={14}
                    style={{ color: "#4f6ef7", flexShrink: 0 }}
                  />
                )}
                {requiresApiKey(skill) && (
                  <Tag
                    color="orange"
                    style={{
                      fontSize: 11,
                      lineHeight: "18px",
                      padding: "0 6px",
                      margin: 0,
                      flexShrink: 0,
                    }}
                  >
                    {t("skills.requiresApiKey")}
                  </Tag>
                )}
              </div>
              <div className={styles.hubCardDesc}>
                {skillDesc(skill) || t("skills.noDescription")}
              </div>
              <div className={styles.hubCardFooter}>
                {typeof skill.downloads === "number" && (
                  <span className={styles.hubCardStat}>
                    <Download size={14} /> {skill.downloads.toLocaleString()}
                  </span>
                )}
                <Button
                  size="small"
                  type={isInstalled(skill.slug) ? "default" : "primary"}
                  icon={
                    isInstalled(skill.slug) ? (
                      <RefreshCw size={14} />
                    ) : (
                      <Download size={14} />
                    )
                  }
                  loading={installingSlug === skill.slug}
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleInstall(skill);
                  }}
                >
                  {isInstalled(skill.slug)
                    ? t("skills.reinstall")
                    : t("skills.install")}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail drawer */}
      <SkillHubDetailDrawer
        open={drawerOpen}
        skill={selectedSkill}
        onClose={() => setDrawerOpen(false)}
        onInstall={(skill) => void handleInstall(skill)}
        installing={installingSlug === selectedSkill?.slug}
        isInstalled={!!selectedSkill && isInstalled(selectedSkill.slug)}
      />
    </div>
  );
}
