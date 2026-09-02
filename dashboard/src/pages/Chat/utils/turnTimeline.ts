import type { ChatMessage } from "../hooks/useChat";
import { deriveMessageContent } from "./messageContent";
import type { MessageGroup } from "./messageGrouping";

export const TURN_TIMELINE_MIN_TURNS = 2;
export const TURN_TIMELINE_MIN_WIDTH_PX = 864;
export const TURN_TIMELINE_MAX_PREVIEW_CHARS = 220;
export const TURN_TIMELINE_MAX_PREVIEW_PARAGRAPHS = 2;
export const TURN_TIMELINE_ROW_PX = 14;
/** Window ticks when the rail grows past this many user turns. */
export const TURN_TIMELINE_VIRTUALIZE_THRESHOLD = 40;
export const TURN_TIMELINE_RAIL_OVERSCAN = 6;
export const TURN_TIMELINE_HOVER_OPEN_DELAY_S = 0.12;
export const TURN_TIMELINE_HOVER_CLOSE_DELAY_S = 0.08;

export interface TurnTimelineItem {
  messageId: string;
  groupIndex: number;
  userPreview: string;
  assistantPreview: string;
  assistantPreviewKind: "text" | "empty" | "running";
  isRunning: boolean;
}

export interface TurnTickVisual {
  colorTone: "focus" | "muted";
  opacity: number;
  scaleX: number;
  tone: "peak" | "near" | "mid" | "idle";
}

export interface TurnTimelinePreviewCopy {
  userFallback: string;
  emptyAssistant: string;
  runningAssistant: string;
}

function splitPreviewParagraphs(text: string, maxParagraphs: number): string[] {
  return text
    .trim()
    .split(/\n\s*\n/u)
    .map((part) => part.replace(/\s+/gu, " ").trim())
    .filter(Boolean)
    .slice(0, Math.max(1, maxParagraphs));
}

export function truncatePreviewText(
  texts: string[],
  fallback: string,
  maxChars = TURN_TIMELINE_MAX_PREVIEW_CHARS,
  maxParagraphs = TURN_TIMELINE_MAX_PREVIEW_PARAGRAPHS,
): string {
  const paragraphs = splitPreviewParagraphs(texts.join("\n\n"), maxParagraphs);
  if (paragraphs.length === 0) return fallback;
  const joined = paragraphs.join("\n");
  const limit = Math.max(8, maxChars);
  if (joined.length <= limit) return joined;
  return `${joined.slice(0, limit - 3).trimEnd()}...`;
}

export function tickVisualForDistance(
  itemIndex: number,
  visualFocusItemIndex: number | undefined,
): TurnTickVisual {
  if (visualFocusItemIndex === undefined) {
    return { colorTone: "muted", opacity: 0.58, scaleX: 1, tone: "idle" };
  }
  const distance = Math.abs(itemIndex - visualFocusItemIndex);
  if (distance === 0) {
    return { colorTone: "focus", opacity: 1, scaleX: 2.6, tone: "peak" };
  }
  if (distance === 1) {
    return { colorTone: "muted", opacity: 0.86, scaleX: 1.7, tone: "near" };
  }
  if (distance === 2) {
    return { colorTone: "muted", opacity: 0.72, scaleX: 1.25, tone: "mid" };
  }
  return { colorTone: "muted", opacity: 0.58, scaleX: 1, tone: "idle" };
}

export function resolveActiveTurnId(args: {
  positions: Array<{ messageId: string; start: number; end: number }>;
  scrollOffsetPx: number;
  viewportHeightPx: number;
}): string | undefined {
  const { positions, scrollOffsetPx, viewportHeightPx } = args;
  if (positions.length === 0) return undefined;
  const viewportStart = Math.max(0, scrollOffsetPx);
  const viewportEnd = viewportStart + Math.max(1, viewportHeightPx);
  const normalized = positions
    .map((row) => {
      const start = Math.max(0, row.start);
      return {
        messageId: row.messageId,
        start,
        end: Math.max(start, row.end),
      };
    })
    .sort(
      (a, b) => a.start - b.start || a.messageId.localeCompare(b.messageId),
    );
  const visible = normalized.filter(
    (row) => row.end >= viewportStart && row.start <= viewportEnd,
  );
  if (visible.length > 0) {
    return visible.reduce((best, row) =>
      Math.abs(row.start - viewportStart) < Math.abs(best.start - viewportStart)
        ? row
        : best,
    ).messageId;
  }
  return (
    [...normalized].reverse().find((row) => row.start <= viewportStart)
      ?.messageId ??
    normalized.find((row) => row.start > viewportStart)?.messageId
  );
}

function messageText(message: ChatMessage): string {
  return deriveMessageContent(message).textContent.trim();
}

export function buildTurnTimelineItems(
  messages: ChatMessage[],
  messageGroups: MessageGroup[],
  copy: TurnTimelinePreviewCopy,
  opts?: { isStreaming?: boolean },
): TurnTimelineItem[] {
  const groupIndexByMessageId = new Map<string, number>();
  messageGroups.forEach((group, index) => {
    for (const msg of group.messages) {
      groupIndexByMessageId.set(msg.id, index);
    }
  });

  const items: TurnTimelineItem[] = [];
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role !== "user") continue;
    const groupIndex = groupIndexByMessageId.get(msg.id);
    if (groupIndex === undefined) continue;

    let assistant: ChatMessage | undefined;
    for (let j = i + 1; j < messages.length; j++) {
      const next = messages[j];
      if (next.role === "user") break;
      if (next.role === "assistant" && messageText(next)) {
        assistant = next;
      }
    }

    const isLastUser = !messages
      .slice(i + 1)
      .some((candidate) => candidate.role === "user");
    const isRunning = Boolean(
      opts?.isStreaming &&
        isLastUser &&
        (!assistant || assistant.status === "streaming"),
    );

    let assistantPreviewKind: TurnTimelineItem["assistantPreviewKind"] =
      "empty";
    let assistantPreview = copy.emptyAssistant;
    if (assistant && messageText(assistant)) {
      assistantPreviewKind = "text";
      assistantPreview = truncatePreviewText(
        [messageText(assistant)],
        copy.emptyAssistant,
      );
    } else if (isRunning) {
      assistantPreviewKind = "running";
      assistantPreview = copy.runningAssistant;
    }

    items.push({
      messageId: msg.id,
      groupIndex,
      userPreview: truncatePreviewText([messageText(msg)], copy.userFallback),
      assistantPreview,
      assistantPreviewKind,
      isRunning,
    });
  }
  return items;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function alignElementToScrollerTop(
  scroller: HTMLElement,
  target: HTMLElement,
  behavior: ScrollBehavior,
): void {
  const top =
    scroller.scrollTop +
    target.getBoundingClientRect().top -
    scroller.getBoundingClientRect().top;
  if (behavior === "auto") {
    scroller.scrollTop = top;
    return;
  }
  scroller.scrollTo({ top, behavior });
}

/** Fallback height for virtualized turns that are not mounted yet. */
export const TURN_TIMELINE_ESTIMATED_UNIT_HEIGHT_PX = 140;

/**
 * Fill in scroll positions for turns whose DOM nodes are not mounted
 * (Virtuoso windowing) by interpolating from nearest measured neighbors.
 */
export function mergeTurnPositions(args: {
  turns: Array<{ messageId: string; groupIndex: number }>;
  measured: Array<{ messageId: string; start: number; end: number }>;
  estimatedUnitHeight?: number;
}): Array<{ messageId: string; start: number; end: number }> {
  const unit = Math.max(
    1,
    args.estimatedUnitHeight ?? TURN_TIMELINE_ESTIMATED_UNIT_HEIGHT_PX,
  );
  const measuredById = new Map(
    args.measured.map((row) => [row.messageId, row] as const),
  );
  const measuredByGroup = new Map<
    number,
    { start: number; end: number; groupIndex: number }
  >();
  for (const turn of args.turns) {
    const known = measuredById.get(turn.messageId);
    if (!known) continue;
    measuredByGroup.set(turn.groupIndex, {
      start: known.start,
      end: known.end,
      groupIndex: turn.groupIndex,
    });
  }

  return args.turns.map((turn) => {
    const known = measuredById.get(turn.messageId);
    if (known) return known;

    let nearest:
      | { dist: number; start: number; end: number; groupIndex: number }
      | undefined;
    for (const candidate of measuredByGroup.values()) {
      const dist = Math.abs(candidate.groupIndex - turn.groupIndex);
      if (!nearest || dist < nearest.dist) {
        nearest = { ...candidate, dist };
      }
    }

    if (nearest) {
      const delta = (turn.groupIndex - nearest.groupIndex) * unit;
      const start = nearest.start + delta;
      return {
        messageId: turn.messageId,
        start,
        end: start + unit,
      };
    }

    const start = turn.groupIndex * unit;
    return {
      messageId: turn.messageId,
      start,
      end: start + unit,
    };
  });
}

/** Prefer the latest turn while the list is pinned to the bottom / following. */
export function resolveFollowPinnedTurnId(
  turns: Array<{ messageId: string }>,
  options: { following: boolean },
): string | undefined {
  if (!options.following || turns.length === 0) return undefined;
  return turns[turns.length - 1]?.messageId;
}

export function resolveFlashTarget(anchor: HTMLElement): HTMLElement {
  const bubble =
    anchor.querySelector<HTMLElement>('[class*="userBubble"]') ??
    anchor.querySelector<HTMLElement>('[class*="messageBubble"]');
  return bubble ?? anchor;
}

/** Inclusive-exclusive window of tick indices to mount in the rail. */
export function visibleTurnWindow(args: {
  count: number;
  scrollTop: number;
  viewportHeight: number;
  rowPx?: number;
  overscan?: number;
  forceFull?: boolean;
}): { start: number; end: number } {
  const count = Math.max(0, args.count);
  if (count === 0) return { start: 0, end: 0 };
  if (args.forceFull) return { start: 0, end: count };
  const rowPx = Math.max(1, args.rowPx ?? TURN_TIMELINE_ROW_PX);
  const overscan = Math.max(0, args.overscan ?? TURN_TIMELINE_RAIL_OVERSCAN);
  const start = Math.max(0, Math.floor(args.scrollTop / rowPx) - overscan);
  const end = Math.min(
    count,
    Math.ceil((args.scrollTop + Math.max(1, args.viewportHeight)) / rowPx) +
      overscan,
  );
  return { start, end: Math.max(start, end) };
}

export function readElementDirection(
  el: Element | null | undefined,
): "ltr" | "rtl" {
  if (typeof document === "undefined") return "ltr";
  const withDir =
    el && typeof el.closest === "function" ? el.closest("[dir]") : null;
  const attr = (
    withDir?.getAttribute("dir") ||
    document.documentElement.getAttribute("dir") ||
    ""
  ).toLowerCase();
  if (attr === "rtl" || attr === "ltr") return attr;
  if (typeof getComputedStyle === "function" && el) {
    const computed = getComputedStyle(el).direction.toLowerCase();
    if (computed === "rtl") return "rtl";
  }
  return "ltr";
}
