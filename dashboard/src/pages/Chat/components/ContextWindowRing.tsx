import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Popover, Spin, Drawer } from "antd";
import {
  octopThreadsApi,
  type ContextUsageBreakdown,
  type ContextUsageSegmentKey,
} from "../../../api/modules/octopThreads";
import { isPendingThread } from "../hooks/useSessions";
import { contextUsedPercent } from "../hooks/useChatContextWindow";
import styles from "../index.module.less";

const DEFAULT_MAX = 128_000;
const BREAKDOWN_CACHE_TTL_MS = 30_000;

const SEGMENT_COLORS: Record<ContextUsageSegmentKey, string> = {
  system_prompt: "#9ca3af",
  tool_definitions: "#c4b5fd",
  rules: "#86efac",
  skills: "#fbbf24",
  mcp: "#e879f9",
  subagent_definitions: "#3b82f6",
  conversation: "#22d3ee",
};

function formatTokenK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

interface ContextWindowRingProps {
  usedTokens: number | null;
  /** No provider usage_metadata — ring/breakdown are local estimates. */
  usageEstimated?: boolean;
  maxTokens: number;
  agentId?: string | null;
  threadId?: string | null;
  selectedConnectors?: string[];
  isMobile?: boolean;
  /** Live-turn flag: a true→false edge refetches the snapshot. */
  isStreaming?: boolean;
}

export default function ContextWindowRing({
  usedTokens,
  usageEstimated = false,
  maxTokens,
  agentId,
  threadId,
  selectedConnectors = [],
  isMobile = false,
  isStreaming = false,
}: ContextWindowRingProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [breakdown, setBreakdown] = useState<ContextUsageBreakdown | null>(
    null,
  );
  const cacheRef = useRef<{
    key: string;
    at: number;
    hint: number;
    data: ContextUsageBreakdown;
  } | null>(null);
  // Stream hint — kept in a ref so prefetch does not re-fire on every token tick.
  const hintUsedRef = useRef(usedTokens ?? 0);
  hintUsedRef.current = usedTokens ?? 0;
  // /compact lowers server usage with no model call, so the hint never
  // drops on its own. Each snapshot records the hint it absorbed; request
  // order decides which of two in-flight responses may land.
  const breakdownHintRef = useRef<number | null>(null);
  const requestSeqRef = useRef(0);

  const max = maxTokens > 0 ? maxTokens : DEFAULT_MAX;
  const hintUsed = usedTokens ?? 0;

  const cacheKey = useMemo(
    () =>
      [
        agentId ?? "",
        threadId ?? "",
        String(max),
        selectedConnectors.join(","),
      ].join("|"),
    [agentId, threadId, max, selectedConnectors],
  );

  const loadBreakdown = useCallback(
    async (opts?: { silent?: boolean; force?: boolean }) => {
      if (!agentId || !threadId || isPendingThread(threadId)) return;
      const force = Boolean(opts?.force);
      const cached = cacheRef.current;
      if (
        !force &&
        cached &&
        cached.key === cacheKey &&
        Date.now() - cached.at < BREAKDOWN_CACHE_TTL_MS
      ) {
        breakdownHintRef.current = cached.hint;
        setBreakdown(cached.data);
        return;
      }
      const reqSeq = ++requestSeqRef.current;
      if (!opts?.silent) setLoading(true);
      try {
        // Prefer a pure harness snapshot. Pass stream hint only as a fallback
        // when we do not already have a segmented breakdown cached.
        const haveSegments =
          cached?.key === cacheKey &&
          (cached.data.segments?.length ?? 0) > 0 &&
          cached.data.used_tokens > 0;
        const hint = hintUsedRef.current;
        const data = await octopThreadsApi.contextUsage(agentId, threadId, {
          maxTokens: max,
          inputTokens: !haveSegments && hint > 0 ? hint : undefined,
          mcpServers: selectedConnectors,
        });
        // A newer request, or a thread switch, already superseded this one.
        if (reqSeq !== requestSeqRef.current) return;
        if (data.used_tokens > 0) {
          cacheRef.current = { key: cacheKey, at: Date.now(), hint, data };
          breakdownHintRef.current = hint;
          setBreakdown(data);
        } else {
          // Empty harness snapshot (old threads) must not pin the ring at 0%.
          cacheRef.current = null;
          breakdownHintRef.current = null;
          setBreakdown(null);
        }
      } catch {
        if (force) {
          // A failed post-compaction refetch must not leave the pre-compaction
          // snapshot cached; dropping it forces the next read to hit the server.
          cacheRef.current = null;
          breakdownHintRef.current = null;
        }
        if (!opts?.silent) setBreakdown(null);
      } finally {
        if (!opts?.silent) setLoading(false);
      }
    },
    [agentId, threadId, max, selectedConnectors, cacheKey],
  );

  // Reset detail cache on thread/filter changes. The ring itself keeps growing
  // from the live/persisted token hint and never needs a checkpoint read.
  useEffect(() => {
    setBreakdown(null);
    cacheRef.current = null;
    breakdownHintRef.current = null;
    // Invalidate anything still in flight for the previous key.
    requestSeqRef.current += 1;
  }, [cacheKey]);

  // Refetch on streaming→idle: the turn may have compacted server-side.
  const wasStreamingRef = useRef(isStreaming);
  useEffect(() => {
    const wasStreaming = wasStreamingRef.current;
    wasStreamingRef.current = isStreaming;
    if (wasStreaming && !isStreaming) {
      void loadBreakdown({ force: true, silent: true });
    }
  }, [isStreaming, loadBreakdown]);

  const ringUsed = useMemo(() => {
    const hasBreakdown = breakdown != null && breakdown.used_tokens > 0;
    const breakdownMax =
      breakdown && breakdown.max_tokens > 0 ? breakdown.max_tokens : max;
    // The snapshot is authoritative while the hint has not moved since it was
    // fetched; a moved hint means the turn outran the snapshot.
    if (hasBreakdown && hintUsed === breakdownHintRef.current) {
      return Math.min(breakdown.used_tokens, breakdownMax);
    }
    if (hintUsed > 0) return Math.min(hintUsed, max);
    if (hasBreakdown) return Math.min(breakdown.used_tokens, breakdownMax);
    // Until prefetch returns, show last-call hint (capped so a stale
    // turn-sum cannot flash a full ring).
    return 0;
  }, [breakdown, hintUsed, max]);

  const ringMax =
    breakdown && breakdown.max_tokens > 0 ? breakdown.max_tokens : max;

  const { usedPct, strokeColor, dashOffset, circumference } = useMemo(() => {
    const usedRatio = ringMax > 0 ? Math.min(ringUsed / ringMax, 1) : 0;
    const usedPercent = contextUsedPercent(ringUsed, ringMax);
    const r = 13;
    const circ = 2 * Math.PI * r;
    let color = "var(--fn-color-success, #22c55e)";
    if (usedRatio >= 0.8) {
      color = "var(--fn-color-danger, #ef4444)";
    } else if (usedRatio >= 0.5) {
      color = "var(--fn-color-warning, #eab308)";
    }
    return {
      usedPct: usedPercent,
      strokeColor: color,
      dashOffset: circ * (1 - usedRatio),
      circumference: circ,
    };
  }, [ringUsed, ringMax]);

  const tooltip = t("chat.contextWindow.tooltip", {
    used: formatTokenK(ringUsed),
    max: formatTokenK(ringMax),
    percent: usedPct,
  });

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) {
      void loadBreakdown();
    }
  };

  const display = breakdown ?? {
    max_tokens: ringMax,
    used_tokens: ringUsed,
    segments: [] as ContextUsageBreakdown["segments"],
  };
  const displayUsed = display.used_tokens > 0 ? display.used_tokens : ringUsed;
  const displayMax = display.max_tokens > 0 ? display.max_tokens : ringMax;
  const displayPct = contextUsedPercent(displayUsed, displayMax);
  const segments =
    display.segments.length > 0
      ? display.segments
      : displayUsed > 0
      ? ([
          { key: "conversation", tokens: displayUsed },
        ] as ContextUsageBreakdown["segments"])
      : display.segments;
  const segmentTotal = segments.reduce((sum, item) => sum + item.tokens, 0);

  const popoverContent = (
    <div className={styles.contextUsagePanel}>
      <div className={styles.contextUsageTitle}>
        {t("chat.contextWindow.breakdownTitle")}
      </div>
      <div className={styles.contextUsageSubtitle}>
        {t("chat.contextWindow.breakdownPercent", { percent: displayPct })}
      </div>
      <div className={styles.contextUsageHint}>
        {usageEstimated
          ? t("chat.contextWindow.estimateHint")
          : t("chat.contextWindow.breakdownHint")}
      </div>
      {loading ? (
        <div className={styles.contextUsageLoading}>
          <Spin size="small" />
        </div>
      ) : (
        <>
          <div
            className={styles.contextUsageBar}
            role="img"
            aria-label={t("chat.contextWindow.breakdownTitle")}
          >
            {segmentTotal > 0 ? (
              segments.map((segment) => (
                <span
                  key={segment.key}
                  className={styles.contextUsageBarSegment}
                  style={{
                    // Provider input usage owns the total bar width. Segment
                    // estimates contribute only their relative composition.
                    flexGrow: (displayUsed * segment.tokens) / segmentTotal,
                    background: SEGMENT_COLORS[segment.key],
                  }}
                />
              ))
            ) : (
              <span
                className={styles.contextUsageBarSegment}
                style={{
                  flexGrow: displayUsed,
                  background: strokeColor,
                }}
              />
            )}
            <span
              className={styles.contextUsageBarRemainder}
              style={{ flexGrow: Math.max(displayMax - displayUsed, 0) }}
            />
          </div>
          <ul className={styles.contextUsageLegend}>
            {segments.map((segment) => (
              <li key={segment.key} className={styles.contextUsageLegendItem}>
                <span
                  className={styles.contextUsageLegendSwatch}
                  style={{ background: SEGMENT_COLORS[segment.key] }}
                />
                <span className={styles.contextUsageLegendLabel}>
                  {t(`chat.contextWindow.segments.${segment.key}`)}
                </span>
                <span className={styles.contextUsageLegendValue}>
                  ~{formatTokenK(segment.tokens)}
                </span>
              </li>
            ))}
            {segments.length === 0 && (
              <li className={styles.contextUsageLegendItem}>
                <span className={styles.contextUsageLegendLabel}>
                  {tooltip}
                </span>
              </li>
            )}
          </ul>
        </>
      )}
    </div>
  );

  const ringInner = (
    <>
      <svg className={styles.contextRingSvg} viewBox="0 0 32 32" aria-hidden>
        <circle
          className={styles.contextRingTrack}
          cx="16"
          cy="16"
          r="13"
          fill="none"
          strokeWidth="3"
        />
        <circle
          className={styles.contextRingProgress}
          cx="16"
          cy="16"
          r="13"
          fill="none"
          strokeWidth="3"
          stroke={strokeColor}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform="rotate(-90 16 16)"
        />
      </svg>
      <span className={styles.contextRingLabel}>{usedPct}</span>
    </>
  );

  const ring = (
    <div
      className={styles.contextRingBtn}
      role="progressbar"
      aria-valuenow={usedPct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={tooltip}
    >
      {ringInner}
    </div>
  );

  if (!agentId || !threadId) {
    return ring;
  }

  if (isMobile) {
    return (
      <>
        <button
          type="button"
          className={styles.contextRingBtn}
          onClick={() => handleOpenChange(true)}
          aria-label={tooltip}
        >
          {ringInner}
        </button>
        <Drawer
          open={open}
          onClose={() => handleOpenChange(false)}
          placement="bottom"
          height="auto"
          title={t("chat.contextWindow.breakdownTitle")}
          className={styles.mobilePickerDrawer}
          styles={{
            body: {
              padding: "12px 16px calc(16px + env(safe-area-inset-bottom))",
            },
          }}
          destroyOnHidden
        >
          {popoverContent}
        </Drawer>
      </>
    );
  }

  return (
    <Popover
      content={popoverContent}
      trigger="click"
      open={open}
      onOpenChange={handleOpenChange}
      placement="topRight"
      overlayClassName={styles.contextUsagePopover}
    >
      {ring}
    </Popover>
  );
}
