import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type RefObject,
} from "react";
import { Popover } from "antd";
import type { VirtuosoHandle } from "react-virtuoso";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../hooks/useChat";
import type { MessageGroup } from "../utils/messageGrouping";
import {
  TURN_TIMELINE_HOVER_CLOSE_DELAY_S,
  TURN_TIMELINE_HOVER_OPEN_DELAY_S,
  TURN_TIMELINE_MIN_TURNS,
  TURN_TIMELINE_MIN_WIDTH_PX,
  TURN_TIMELINE_ROW_PX,
  TURN_TIMELINE_VIRTUALIZE_THRESHOLD,
  alignElementToScrollerTop,
  buildTurnTimelineItems,
  mergeTurnPositions,
  prefersReducedMotion,
  readElementDirection,
  resolveActiveTurnId,
  resolveFlashTarget,
  resolveFollowPinnedTurnId,
  tickVisualForDistance,
  visibleTurnWindow,
  type TurnTimelineItem,
} from "../utils/turnTimeline";
import styles from "./TurnTimelineRail.module.less";

const FLASH_CLASS = "turn-timeline-flash";
const FLASH_MS = 700;
const JUMP_RETRY_FRAMES = 30;

interface TurnTimelineRailProps {
  messages: ChatMessage[];
  messageGroups: MessageGroup[];
  isStreaming?: boolean;
  /** When true (pinned near bottom), keep the latest tick active. */
  following?: boolean;
  useVirtual: boolean;
  firstItemIndex: number;
  scrollerRef: RefObject<HTMLElement | null>;
  containerRef: RefObject<HTMLDivElement | null>;
  virtuosoRef: RefObject<VirtuosoHandle | null>;
  bubbleRefsMap: MutableRefObject<Map<string, HTMLDivElement>>;
  wrapperRef: RefObject<HTMLDivElement | null>;
  armProgrammaticGuard: (ms?: number) => void;
  onVisibilityChange?: (visible: boolean) => void;
}

function flashElement(anchor: HTMLElement): void {
  const el = resolveFlashTarget(anchor);
  el.classList.remove(FLASH_CLASS);
  void el.offsetWidth;
  el.classList.add(FLASH_CLASS);
  window.setTimeout(() => {
    el.classList.remove(FLASH_CLASS);
  }, FLASH_MS);
}

export default function TurnTimelineRail({
  messages,
  messageGroups,
  isStreaming,
  following = false,
  useVirtual,
  firstItemIndex,
  scrollerRef,
  containerRef,
  virtuosoRef,
  bubbleRefsMap,
  wrapperRef,
  armProgrammaticGuard,
  onVisibilityChange,
}: TurnTimelineRailProps) {
  const { t } = useTranslation();
  const railScrollRef = useRef<HTMLDivElement | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | undefined>(undefined);
  const [activeMessageId, setActiveMessageId] = useState<string | undefined>(
    undefined,
  );
  const [wideEnough, setWideEnough] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [textDirection, setTextDirection] = useState<"ltr" | "rtl">("ltr");
  const [railViewport, setRailViewport] = useState({
    scrollTop: 0,
    height: 0,
  });

  const turns = useMemo(
    () =>
      buildTurnTimelineItems(
        messages,
        messageGroups,
        {
          userFallback: t("chat.turnTimeline.userFallback"),
          emptyAssistant: t("chat.turnTimeline.emptyAssistant"),
          runningAssistant: t("chat.turnTimeline.runningAssistant"),
        },
        { isStreaming },
      ),
    [messages, messageGroups, isStreaming, t],
  );

  const showRail = wideEnough && turns.length >= TURN_TIMELINE_MIN_TURNS;

  useEffect(() => {
    onVisibilityChange?.(showRail);
  }, [showRail, onVisibilityChange]);

  useEffect(() => {
    setReducedMotion(prefersReducedMotion());
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReducedMotion(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const update = () => {
      setWideEnough(el.clientWidth >= TURN_TIMELINE_MIN_WIDTH_PX);
      setTextDirection(readElementDirection(el));
    };
    update();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }
    const ro = new ResizeObserver(update);
    ro.observe(el);
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["dir"],
    });
    return () => {
      ro.disconnect();
      mo.disconnect();
    };
  }, [wrapperRef]);

  useEffect(() => {
    const el = railScrollRef.current;
    if (!el || !showRail) return;
    const sync = () => {
      setRailViewport({
        scrollTop: el.scrollTop,
        height: el.clientHeight,
      });
    };
    sync();
    el.addEventListener("scroll", sync, { passive: true });
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", sync);
      return () => {
        el.removeEventListener("scroll", sync);
        window.removeEventListener("resize", sync);
      };
    }
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", sync);
      ro.disconnect();
    };
  }, [showRail, turns.length]);

  const getScroller = useCallback((): HTMLElement | null => {
    if (useVirtual) return scrollerRef.current;
    return containerRef.current;
  }, [useVirtual, scrollerRef, containerRef]);

  const measureActive = useCallback(() => {
    const pinned = resolveFollowPinnedTurnId(turns, { following });
    if (pinned) {
      setActiveMessageId(pinned);
      return;
    }

    const scroller = getScroller();
    if (!scroller || turns.length === 0) {
      setActiveMessageId(undefined);
      return;
    }
    const scrollerRect = scroller.getBoundingClientRect();
    const measured: Array<{ messageId: string; start: number; end: number }> =
      [];
    for (const turn of turns) {
      const el =
        bubbleRefsMap.current.get(turn.messageId) ??
        (scroller.querySelector(
          `[data-message-id="${CSS.escape(turn.messageId)}"]`,
        ) as HTMLElement | null);
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      const start = scroller.scrollTop + rect.top - scrollerRect.top;
      measured.push({
        messageId: turn.messageId,
        start,
        end: start + rect.height,
      });
    }
    const positions = mergeTurnPositions({ turns, measured });
    setActiveMessageId(
      resolveActiveTurnId({
        positions,
        scrollOffsetPx: scroller.scrollTop,
        viewportHeightPx: scroller.clientHeight,
      }),
    );
  }, [bubbleRefsMap, following, getScroller, turns]);

  useEffect(() => {
    const scroller = getScroller();
    if (!scroller) return;
    const onScroll = () => {
      measureActive();
    };
    measureActive();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, [getScroller, measureActive, messages.length, useVirtual]);

  const activeIndex = useMemo(() => {
    if (!activeMessageId) return -1;
    return turns.findIndex((turn) => turn.messageId === activeMessageId);
  }, [activeMessageId, turns]);

  useEffect(() => {
    if (!showRail || activeIndex < 0 || turns.length < 2) return;
    const scroller = railScrollRef.current;
    if (!scroller) return;
    const rowTop = activeIndex * TURN_TIMELINE_ROW_PX;
    const rowBottom = rowTop + TURN_TIMELINE_ROW_PX;
    if (rowTop < scroller.scrollTop) {
      scroller.scrollTop = rowTop;
    } else if (rowBottom > scroller.scrollTop + scroller.clientHeight) {
      scroller.scrollTop = rowBottom - scroller.clientHeight;
    }
  }, [activeIndex, showRail, turns.length]);

  const jumpToTurn = useCallback(
    (turn: TurnTimelineItem) => {
      const scroller = getScroller();
      if (!scroller) return;
      armProgrammaticGuard(reducedMotion ? 200 : 450);
      const behavior: ScrollBehavior = reducedMotion ? "auto" : "smooth";

      const tryAlign = (): boolean => {
        const target =
          bubbleRefsMap.current.get(turn.messageId) ??
          (scroller.querySelector(
            `[data-message-id="${CSS.escape(turn.messageId)}"]`,
          ) as HTMLElement | null);
        if (!target) return false;
        alignElementToScrollerTop(scroller, target, behavior);
        flashElement(target);
        measureActive();
        return true;
      };

      if (tryAlign()) return;

      if (useVirtual) {
        virtuosoRef.current?.scrollToIndex({
          index: firstItemIndex + turn.groupIndex,
          align: "start",
          behavior: "auto",
        });
        let attempts = JUMP_RETRY_FRAMES;
        const retry = () => {
          if (tryAlign() || --attempts <= 0) return;
          window.requestAnimationFrame(retry);
        };
        window.requestAnimationFrame(retry);
      }
    },
    [
      armProgrammaticGuard,
      bubbleRefsMap,
      firstItemIndex,
      getScroller,
      measureActive,
      reducedMotion,
      useVirtual,
      virtuosoRef,
    ],
  );

  if (turns.length < TURN_TIMELINE_MIN_TURNS) {
    return null;
  }

  const totalHeight = turns.length * TURN_TIMELINE_ROW_PX;
  const forceFull = turns.length < TURN_TIMELINE_VIRTUALIZE_THRESHOLD;
  const tickWindow = visibleTurnWindow({
    count: turns.length,
    scrollTop: railViewport.scrollTop,
    viewportHeight: railViewport.height || totalHeight,
    forceFull,
  });
  const previewPlacement = textDirection === "rtl" ? "leftTop" : "rightTop";

  return (
    <nav
      className={[styles.rail, showRail ? styles.railVisible : ""]
        .filter(Boolean)
        .join(" ")}
      aria-label={t("chat.turnTimeline.label")}
      aria-hidden={!showRail}
      data-testid="turn-timeline-rail"
      data-item-count={turns.length}
      data-visible={showRail ? "true" : "false"}
      data-direction={textDirection}
    >
      <div
        ref={railScrollRef}
        className={styles.railScroll}
        onPointerLeave={() => setHoverIndex(undefined)}
      >
        <div className={styles.railInner} style={{ height: totalHeight }}>
          {turns.slice(tickWindow.start, tickWindow.end).map((turn, offset) => {
            const index = tickWindow.start + offset;
            const isActive = index === activeIndex;
            const visual = tickVisualForDistance(index, hoverIndex);
            const scrollActiveNoHover = hoverIndex === undefined && isActive;
            const opacity = scrollActiveNoHover
              ? 0.9
              : turn.isRunning
              ? Math.max(visual.opacity, 0.72)
              : visual.opacity;
            const scaleX =
              reducedMotion && hoverIndex !== undefined
                ? hoverIndex === index
                  ? 2.6
                  : 1
                : visual.scaleX;
            const barClass = [
              styles.tickBar,
              visual.colorTone === "focus"
                ? styles.tickBarFocus
                : styles.tickBarMuted,
              scrollActiveNoHover ? styles.tickBarActive : "",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <div
                key={turn.messageId}
                className={styles.tickRow}
                style={{
                  transform: `translateY(${index * TURN_TIMELINE_ROW_PX}px)`,
                }}
              >
                <Popover
                  trigger="hover"
                  placement={previewPlacement}
                  arrow={false}
                  mouseEnterDelay={TURN_TIMELINE_HOVER_OPEN_DELAY_S}
                  mouseLeaveDelay={TURN_TIMELINE_HOVER_CLOSE_DELAY_S}
                  overlayClassName={styles.previewOverlay}
                  content={
                    <div className={styles.preview}>
                      <p className={styles.previewUser}>{turn.userPreview}</p>
                      <p
                        className={[
                          styles.previewAssistant,
                          turn.assistantPreviewKind !== "text"
                            ? styles.previewAssistantMuted
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        {turn.assistantPreview}
                      </p>
                    </div>
                  }
                >
                  <button
                    type="button"
                    className={styles.tickButton}
                    aria-current={isActive ? "location" : undefined}
                    aria-label={t("chat.turnTimeline.jumpToQuery", {
                      index: String(index + 1),
                    })}
                    aria-posinset={index + 1}
                    aria-setsize={turns.length}
                    data-testid={`turn-timeline-tick-${index}`}
                    data-message-id={turn.messageId}
                    data-active={isActive ? "true" : "false"}
                    data-running={turn.isRunning ? "true" : "false"}
                    data-visual-tone={visual.tone}
                    onBlur={() => setHoverIndex(undefined)}
                    onFocus={() => setHoverIndex(index)}
                    onPointerEnter={() => setHoverIndex(index)}
                    onPointerLeave={() => setHoverIndex(undefined)}
                    onClick={() => jumpToTurn(turn)}
                  >
                    <span
                      className={barClass}
                      style={{
                        opacity,
                        transform: `scaleX(${scaleX})`,
                      }}
                    />
                  </button>
                </Popover>
              </div>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
