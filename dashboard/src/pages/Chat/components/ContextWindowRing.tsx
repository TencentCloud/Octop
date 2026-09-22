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
  maxTokens: number;
  agentId?: string | null;
  threadId?: string | null;
  selectedConnectors?: string[];
  isMobile?: boolean;
}

export default function ContextWindowRing({
  usedTokens,
  maxTokens,
  agentId,
  threadId,
  selectedConnectors,
  isMobile = false,
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
    data: ContextUsageBreakdown;
  } | null>(null);
  const currentCacheKeyRef = useRef("");

  const max = maxTokens > 0 ? maxTokens : DEFAULT_MAX;
  const connectorKey = selectedConnectors?.join(",") ?? "";

  const cacheKey = useMemo(
    () =>
      [
        agentId ?? "",
        threadId ?? "",
        String(max),
        connectorKey,
        String(usedTokens),
      ].join("|"),
    [agentId, threadId, max, connectorKey, usedTokens],
  );
  currentCacheKeyRef.current = cacheKey;

  const loadBreakdown = useCallback(
    async (opts?: { silent?: boolean; force?: boolean }) => {
      if (!agentId || !threadId || isPendingThread(threadId)) return;
      const cached = cacheRef.current;
      if (
        !opts?.force &&
        cached &&
        cached.key === cacheKey &&
        Date.now() - cached.at < BREAKDOWN_CACHE_TTL_MS
      ) {
        setBreakdown(cached.data);
        return;
      }
      if (!opts?.silent) setLoading(true);
      const requestKey = cacheKey;
      try {
        const data = await octopThreadsApi.contextUsage(agentId, threadId, {
          maxTokens: max,
        });
        if (requestKey !== currentCacheKeyRef.current) return;
        if (data.available === true) {
          cacheRef.current = { key: cacheKey, at: Date.now(), data };
        } else {
          cacheRef.current = null;
        }
        setBreakdown(data);
      } catch {
        if (requestKey === currentCacheKeyRef.current && !opts?.silent) {
          setBreakdown(null);
        }
      } finally {
        if (requestKey === currentCacheKeyRef.current && !opts?.silent) {
          setLoading(false);
        }
      }
    },
    [agentId, threadId, max, cacheKey],
  );

  // Reset on thread/filter changes before requesting the current live snapshot.
  useEffect(() => {
    setBreakdown(null);
    cacheRef.current = null;
  }, [cacheKey]);

  useEffect(() => {
    void loadBreakdown({ silent: true });
  }, [cacheKey, usedTokens, loadBreakdown]);

  const available =
    cacheRef.current?.key === cacheKey && breakdown?.available === true;
  const ringUsed = available ? breakdown.used_tokens : 0;
  const ringMax =
    available && breakdown.max_tokens > 0 ? breakdown.max_tokens : max;

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

  const tooltip = available
    ? t("chat.contextWindow.tooltip", {
        used: formatTokenK(ringUsed),
        max: formatTokenK(ringMax),
        percent: usedPct,
      })
    : t("chat.contextWindow.unavailableTooltip", {
        max: formatTokenK(ringMax),
      });

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) {
      void loadBreakdown({ force: true });
    }
  };

  const segments = available ? breakdown.segments : [];
  const segmentTotal = segments.reduce((sum, item) => sum + item.tokens, 0);

  const popoverContent = (
    <div className={styles.contextUsagePanel}>
      <div className={styles.contextUsageTitle}>
        {t("chat.contextWindow.breakdownTitle")}
      </div>
      {available && (
        <div className={styles.contextUsageSubtitle}>
          {t("chat.contextWindow.breakdownPercent", { percent: usedPct })}
        </div>
      )}
      <div className={styles.contextUsageHint}>
        {available ? t("chat.contextWindow.breakdownHint") : tooltip}
      </div>
      {loading ? (
        <div className={styles.contextUsageLoading}>
          <Spin size="small" />
        </div>
      ) : available ? (
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
                    flexGrow: (ringUsed * segment.tokens) / segmentTotal,
                    background: SEGMENT_COLORS[segment.key],
                  }}
                />
              ))
            ) : (
              <span
                className={styles.contextUsageBarSegment}
                style={{
                  flexGrow: ringUsed,
                  background: strokeColor,
                }}
              />
            )}
            <span
              className={styles.contextUsageBarRemainder}
              style={{ flexGrow: Math.max(ringMax - ringUsed, 0) }}
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
          </ul>
        </>
      ) : null}
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
      <span className={styles.contextRingLabel}>
        {available ? usedPct : "—"}
      </span>
    </>
  );

  const ring = available ? (
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
  ) : (
    <div className={styles.contextRingBtn} role="img" aria-label={tooltip}>
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
