/** Live token counter for the chat composer.

 *  - Chip in the actions row shows the current text's BPE token count.
 *  - Clicking the chip opens a popover with this-turn and per-model usage
 *    breakdown (input / output / cache read / cache write).
 *
 *  The composer counter is a pure function of `text`. Per-turn usage is read
 *  from `chatStore.runUsage` for the current session via
 *  `useSyncExternalStore`, so SSE usage chunks keep it fresh without the
 *  component subscribing to the chat stream directly. */

import { memo, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSyncExternalStore } from "react";
import { Popover } from "antd";
import { Coins } from "lucide-react";
import {
  estimateTokens,
  formatTokenCount,
} from "../../../utils/estimateTokens";
import { getSnapshot, subscribe } from "../hooks/chatStore";
import type { TokenUsage } from "../../../api/types/chat";
import styles from "../index.module.less";

interface TokenCounterProps {
  /** Current text in the composer textarea. */
  text: string;
  /** Chat session id (== threadId). When null, run usage is hidden. */
  sessionId?: string | null;
}

interface UsageTotals {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  total: number;
  modelCalls: number;
  /** Cache hit ratio (0–1), or null when no cache data exists yet. */
  cacheHitRate: number | null;
}

function readPositiveNumber(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return 0;
  }
  return value;
}

function usageTotals(usage: TokenUsage | null): UsageTotals {
  if (!usage) {
    return {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      total: 0,
      modelCalls: 0,
      cacheHitRate: null,
    };
  }
  const input = readPositiveNumber(usage.input_tokens);
  const output = readPositiveNumber(usage.output_tokens);
  const cacheRead = readPositiveNumber(usage.cache_read_tokens);
  const cacheWrite = readPositiveNumber(usage.cache_write_tokens);
  const total = readPositiveNumber(usage.total_tokens) || input + output;
  // Cache hit rate = cache_read / (cache_read + uncached_input).
  // Provider-billed `input_tokens` is the union (read + uncached), so it
  // cannot stand alone as the denominator — caching would inflate the
  // rate. Models without prompt caching report neither field; the rate
  // stays null and the UI renders "—" instead of "0%".
  const uncachedInput = readPositiveNumber(usage.uncached_input_tokens);
  const cacheBase = cacheRead + uncachedInput;
  const cacheHitRate =
    cacheBase > 0 ? Math.min(cacheRead / cacheBase, 1) : null;
  return {
    input,
    output,
    cacheRead,
    cacheWrite,
    total,
    modelCalls: readPositiveNumber(usage.model_calls),
    cacheHitRate,
  };
}

/** Render one `<dd>` cell: the primary value plus an optional secondary
 *  hint (e.g. the cache-hit percentage). Centralised so every row keeps
 *  the same placeholder ("—") and the hint styling is owned in one place. */
function formatRowValue(value: number, hint: string | null): ReactNode {
  return (
    <>
      <span>{value > 0 ? formatTokenCount(value) : "—"}</span>
      {hint && (
        <span
          className={styles.tokenCounterPanelRowHint}
          data-testid="token-counter-hint"
        >
          {hint}
        </span>
      )}
    </>
  );
}

function TokenCounter({ text, sessionId }: TokenCounterProps) {
  const { t } = useTranslation();

  // Composer token count is async (lazy BPE table). Hold the previous value
  // while the encoder is warming up so the chip does not flicker to 0.
  const [draftTokens, setDraftTokens] = useState<number>(0);
  useEffect(() => {
    let cancelled = false;
    void estimateTokens(text).then((n) => {
      if (!cancelled) setDraftTokens(n);
    });
    return () => {
      cancelled = true;
    };
  }, [text]);

  // React 18 handles tear-free subscription to external stores. Switching
  // sessionId is automatic: the subscribe closure captures the new id, and
  // getSnapshot re-reads on every notify.
  const runUsage = useSyncExternalStore(
    (cb) => (sessionId ? subscribe(sessionId, cb) : () => {}),
    () => (sessionId ? getSnapshot(sessionId).runUsage ?? null : null),
  );

  const totals = usageTotals(runUsage);
  const showUsage = !!sessionId && totals.modelCalls > 0;

  const chip = (
    <button
      type="button"
      className={styles.tokenCounterChip}
      aria-label={t("chat.tokenCounter.label", {
        tokens: formatTokenCount(draftTokens),
      })}
      data-testid="token-counter-chip"
    >
      <Coins size={14} aria-hidden />
      <span>{formatTokenCount(draftTokens)}</span>
    </button>
  );

  if (!showUsage) {
    return chip;
  }

  // `total: true` styles the totals row with the heavier border + bolder
  // value. `hint` is computed inline (only the cache-hit row carries one)
  // so the row spec stays a single literal per line.
  const rows: Array<{
    label: string;
    value: number;
    total?: boolean;
    hint: string | null;
  }> = [
    { label: t("chat.tokenCounter.input", "输入"), value: totals.input, hint: null },
    { label: t("chat.tokenCounter.output", "输出"), value: totals.output, hint: null },
    {
      label: t("chat.tokenCounter.cacheRead", "缓存命中"),
      value: totals.cacheRead,
      hint:
        totals.cacheHitRate === null
          ? "—"
          : `${Math.round(totals.cacheHitRate * 100)}%`,
    },
    { label: t("chat.tokenCounter.cacheWrite", "缓存写入"), value: totals.cacheWrite, hint: null },
    { label: t("chat.tokenCounter.total", "合计"), value: totals.total, total: true, hint: null },
    { label: t("chat.tokenCounter.modelCalls", "模型调用"), value: totals.modelCalls, hint: null },
  ];

  return (
    <Popover
      trigger="click"
      placement="topRight"
      overlayClassName={styles.tokenCounterPopover}
      content={
        <div
          className={styles.tokenCounterPanel}
          data-testid="token-counter-panel"
        >
          <div className={styles.tokenCounterPanelTitle}>
            {t("chat.tokenCounter.popoverTitle", "本轮用量")}
          </div>
          <dl className={styles.tokenCounterPanelList}>
            {rows.map(({ label, value, total, hint }) => (
              <div
                key={label}
                className={`${styles.tokenCounterPanelRow}${
                  total ? ` ${styles.tokenCounterPanelRowTotal}` : ""
                }`}
              >
                <dt>{label}</dt>
                <dd>{formatRowValue(value, hint)}</dd>
              </div>
            ))}
          </dl>
        </div>
      }
    >
      {chip}
    </Popover>
  );
}

export default memo(TokenCounter);