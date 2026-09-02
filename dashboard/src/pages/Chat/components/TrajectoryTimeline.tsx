import { Tooltip } from "antd";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import { useTranslation } from "react-i18next";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import {
  clamp,
  deriveSwimlaneSpans,
  orderedRange,
  panDomain,
  zoomDomain,
  type SwimlaneSpan,
  type TrajectoryTimeRange,
} from "../utils/trajectoryTimeline";
import styles from "./TrajectoryTimeline.module.less";

const LANE_INDEX = { input: 0, model: 1, tools: 2 } as const;
const MINIMUM_DRAG_PX = 3;
const MINIMUM_ZOOM_OPERATIONS = 4;
const DURATION_MIN_DOMAIN = 20;
const EDGE_PAN_ZONE_FRACTION = 0.08;
const EDGE_PAN_STEP_FRACTION = 0.025;
const MAXIMUM_EDGE_PAN_PX = 32;
const TIMELINE_TOOLTIP_DELAY_S = 0.5;

export type TrajectoryTimelineMode = "sequence" | "duration";

export interface TrajectoryTimelineProps {
  events: TrajectoryEvent[];
  mode: TrajectoryTimelineMode;
  range: TrajectoryTimeRange | null;
  onRangeChange: (range: TrajectoryTimeRange | null) => void;
  selectedEventId: string | null;
  searchMatchIds: ReadonlySet<string> | null;
  hasEarlier?: boolean;
  onLoadEarlier?: () => void | Promise<void>;
  onRecordSelect: (eventId: string) => void;
  onRecordFocus?: (eventId: string) => void;
}

interface HoverPoint {
  fraction: number;
  eventId: string | null;
}

interface DragGesture {
  pointerId: number;
  anchorTime: number;
  anchorClientX: number;
  eventId: string | null;
}

interface PanGesture {
  anchorClientX: number;
  anchorStart: number;
  moved: boolean;
  pannable: boolean;
  pointerId: number;
}

function spanKindAttr(kind: string): string {
  if (kind === "assistant") return "message";
  return kind;
}

function spanPrimaryId(span: SwimlaneSpan): string {
  return span.eventIds[0] ?? span.id;
}

function spanIntersects(
  span: SwimlaneSpan,
  range: TrajectoryTimeRange,
): boolean {
  return span.start <= range.end && span.end >= range.start;
}

function rangeFraction(
  range: TrajectoryTimeRange,
  start: number,
  duration: number,
  minimum: number,
  maximum: number,
): { start: number; end: number } {
  const bounded = orderedRange(
    clamp(range.start, minimum, maximum),
    clamp(range.end, minimum, maximum),
  );
  return {
    start: (bounded.start - start) / duration,
    end: (bounded.end - start) / duration,
  };
}

function centeredRange(
  center: number,
  width: number,
  minimum: number,
  maximum: number,
): TrajectoryTimeRange {
  const clampedWidth = Math.min(maximum - minimum, Math.max(0, width));
  const start = Math.min(
    Math.max(center - clampedWidth / 2, minimum),
    maximum - clampedWidth,
  );
  return { start, end: start + clampedWidth };
}

function eventIdAt(target: EventTarget | null): string | null {
  const el = target instanceof HTMLElement ? target : null;
  const value = el?.closest("[data-event-ids]")?.getAttribute("data-event-ids");
  if (value == null || value === "") return null;
  return value.split(",")[0] ?? null;
}

function nearestSpan(
  spans: readonly SwimlaneSpan[],
  timelinePoint: number,
): SwimlaneSpan | undefined {
  if (spans.length === 0) return undefined;
  const distance = (span: SwimlaneSpan): number => {
    if (timelinePoint < span.start) return span.start - timelinePoint;
    if (timelinePoint > span.end) return timelinePoint - span.end;
    return 0;
  };
  return spans.reduce((candidate, span) =>
    distance(span) < distance(candidate) ? span : candidate,
  );
}

function EarlierHistoryBoundary({
  loading,
  onHover,
  onLoad,
  label,
}: {
  loading: boolean;
  onHover: () => void;
  onLoad: (() => void) | undefined;
  label: string;
}) {
  return (
    <button
      type="button"
      className={styles.earlierHistory}
      aria-label={label}
      aria-disabled={onLoad === undefined}
      disabled={loading || onLoad === undefined}
      onClick={(event) => {
        event.stopPropagation();
        onLoad?.();
      }}
      onPointerEnter={() => {
        onHover();
      }}
      onPointerMove={(event) => {
        event.stopPropagation();
      }}
      onPointerDown={(event) => {
        event.stopPropagation();
      }}
    >
      …
    </button>
  );
}

export default function TrajectoryTimeline({
  events,
  mode,
  range,
  onRangeChange,
  selectedEventId,
  searchMatchIds,
  hasEarlier = false,
  onLoadEarlier,
  onRecordSelect,
  onRecordFocus,
}: TrajectoryTimelineProps) {
  const { t } = useTranslation();
  const spans = useMemo(
    () => deriveSwimlaneSpans(events, mode),
    [events, mode],
  );
  const modelStart = spans.reduce(
    (min, span) => Math.min(min, span.start),
    spans[0]?.start ?? 0,
  );
  const modelEnd = spans.reduce(
    (max, span) => Math.max(max, span.end),
    modelStart + 1,
  );
  const dragRef = useRef<DragGesture | null>(null);
  const panRef = useRef<PanGesture | null>(null);
  const suppressClickRef = useRef(false);
  const rootRef = useRef<HTMLElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [draft, setDraft] = useState<TrajectoryTimeRange | null>(null);
  const [hover, setHover] = useState<HoverPoint | null>(null);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [panning, setPanning] = useState(false);
  const [viewport, setViewport] = useState<TrajectoryTimeRange | null>(null);
  const [animateViewport, setAnimateViewport] = useState(false);

  useEffect(() => {
    if (range !== null && (range.end < modelStart || range.start > modelEnd)) {
      onRangeChange(null);
    }
  }, [modelEnd, modelStart, onRangeChange, range]);

  useEffect(() => {
    setAnimateViewport(false);
    setViewport((current) =>
      current !== null && (current.end < modelStart || current.start > modelEnd)
        ? null
        : current,
    );
  }, [modelEnd, modelStart]);

  useEffect(() => {
    if (selectedEventId === null) return;
    const selectedSpan = spans.find((span) =>
      span.eventIds.includes(selectedEventId),
    );
    if (selectedSpan === undefined) return;
    setAnimateViewport(true);
    setViewport((current) => {
      if (current === null) return current;
      if (
        selectedSpan.end > current.start &&
        selectedSpan.start < current.end
      ) {
        return current;
      }
      const duration = Math.max(1, current.end - current.start);
      const desiredStart =
        selectedSpan.end <= current.start
          ? selectedSpan.start
          : selectedSpan.end - duration;
      const nextStart = Math.min(
        Math.max(desiredStart, modelStart),
        Math.max(modelStart, modelEnd - duration),
      );
      if (nextStart === current.start) return current;
      return { start: nextStart, end: nextStart + duration };
    });
  }, [modelEnd, modelStart, selectedEventId, spans]);

  const fullDuration = Math.max(1, modelEnd - modelStart);
  const viewportDuration = Math.min(
    fullDuration,
    Math.max(1, (viewport?.end ?? 0) - (viewport?.start ?? 0)),
  );
  const viewportStart =
    viewport === null
      ? modelStart
      : Math.min(
          Math.max(viewport.start, modelStart),
          modelEnd - viewportDuration,
        );
  const domainDuration = viewport === null ? fullDuration : viewportDuration;
  const domainStart = viewport === null ? modelStart : viewportStart;
  const showsEarlierBoundary =
    hasEarlier && (spans.length === 0 || domainStart === modelStart);
  const loadEarlier =
    onLoadEarlier === undefined || loadingEarlier
      ? undefined
      : () => {
          setLoadingEarlier(true);
          void Promise.resolve(onLoadEarlier()).finally(() => {
            setLoadingEarlier(false);
          });
        };

  const projectedDomainStyle = {
    "--trajectory-domain-left": `${
      (-(domainStart - modelStart) / domainDuration) * 100
    }%`,
    "--trajectory-domain-width": `${(fullDuration / domainDuration) * 100}%`,
  } as CSSProperties;
  const committed =
    range === null
      ? null
      : rangeFraction(range, domainStart, domainDuration, modelStart, modelEnd);
  const draftFraction =
    draft === null
      ? null
      : rangeFraction(draft, domainStart, domainDuration, modelStart, modelEnd);
  const visibleRange = draftFraction ?? committed;
  const activeRange = draft ?? range;

  useEffect(() => {
    const root = rootRef.current;
    if (root === null) return;
    const onWheel = (event: WheelEvent): void => {
      event.preventDefault();
      const track = trackRef.current;
      if (track === null || spans.length === 0) return;
      setAnimateViewport(false);
      const rect = track.getBoundingClientRect();
      const anchorFraction = clamp(
        (event.clientX - rect.left) / Math.max(1, rect.width),
        0,
        1,
      );
      const next = zoomDomain({
        fullStart: modelStart,
        fullEnd: modelEnd,
        domainStart,
        domainEnd: domainStart + domainDuration,
        anchorFraction,
        zoomFactor: Math.exp(event.deltaY * 0.0015),
        minDomain: Math.min(
          mode === "sequence" ? MINIMUM_ZOOM_OPERATIONS : DURATION_MIN_DOMAIN,
          fullDuration,
        ),
      });
      if (next.end - next.start >= fullDuration * 0.999) {
        setViewport(null);
        return;
      }
      setViewport(next);
    };
    root.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      root.removeEventListener("wheel", onWheel);
    };
  }, [
    domainDuration,
    domainStart,
    fullDuration,
    mode,
    modelEnd,
    modelStart,
    spans.length,
  ]);

  const laneName = {
    input: t("chat.dockTrajectoryLaneInput", "Input"),
    model: t("chat.dockTrajectoryLaneModel", "Model"),
    tools: t("chat.dockTrajectoryLaneTools", "Tools"),
  };
  const earlierLabel = t(
    "chat.dockTrajectoryLoadEarlier",
    "Load earlier history",
  );

  const fractionAt = (event: PointerEvent<HTMLDivElement>): number => {
    const rect = event.currentTarget.getBoundingClientRect();
    return clamp((event.clientX - rect.left) / Math.max(1, rect.width), 0, 1);
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button === 2) {
      panRef.current = {
        anchorClientX: event.clientX,
        anchorStart: domainStart,
        moved: false,
        pannable: viewport !== null,
        pointerId: event.pointerId,
      };
      if (viewport !== null) setAnimateViewport(false);
      setPanning(true);
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (event.button !== 0 || spans.length === 0) return;
    const anchor = fractionAt(event);
    const anchorTime = domainStart + anchor * domainDuration;
    const eventId = eventIdAt(event.target);
    setHover({ fraction: anchor, eventId });
    dragRef.current = {
      pointerId: event.pointerId,
      anchorTime,
      anchorClientX: event.clientX,
      eventId,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDraft({ start: anchorTime, end: anchorTime });
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const fraction = fractionAt(event);
    setHover({ fraction, eventId: eventIdAt(event.target) });
    const pan = panRef.current;
    if (pan !== null && pan.pointerId === event.pointerId) {
      if (Math.abs(event.clientX - pan.anchorClientX) >= MINIMUM_DRAG_PX) {
        pan.moved = true;
      }
      if (!pan.pannable) return;
      setViewport(
        panDomain({
          fullStart: modelStart,
          fullEnd: modelEnd,
          domainStart: pan.anchorStart,
          domainEnd: pan.anchorStart + domainDuration,
          deltaFraction:
            -(event.clientX - pan.anchorClientX) / Math.max(1, rect.width),
        }),
      );
      return;
    }
    const drag = dragRef.current;
    if (drag === null || drag.pointerId !== event.pointerId) return;
    let nextDomainStart = domainStart;
    if (viewport !== null) {
      const localX = event.clientX - rect.left;
      const edgeWidth = Math.min(
        MAXIMUM_EDGE_PAN_PX,
        Math.max(1, rect.width * EDGE_PAN_ZONE_FRACTION),
      );
      const direction =
        localX < edgeWidth ? -1 : localX > rect.width - edgeWidth ? 1 : 0;
      if (direction !== 0) {
        const edgeDistance =
          direction < 0
            ? edgeWidth - localX
            : localX - (rect.width - edgeWidth);
        const strength = clamp(edgeDistance / edgeWidth, 0, 1);
        const desiredStart =
          domainStart +
          direction *
            domainDuration *
            EDGE_PAN_STEP_FRACTION *
            Math.max(0.2, strength);
        nextDomainStart = Math.min(
          Math.max(desiredStart, modelStart),
          modelEnd - domainDuration,
        );
        if (nextDomainStart !== domainStart) {
          setAnimateViewport(false);
          setViewport({
            start: nextDomainStart,
            end: nextDomainStart + domainDuration,
          });
        }
      }
    }
    const pointTime = nextDomainStart + fraction * domainDuration;
    setDraft(orderedRange(drag.anchorTime, pointTime));
  };

  const onPointerEnd = (event: PointerEvent<HTMLDivElement>) => {
    const pan = panRef.current;
    if (pan !== null && pan.pointerId === event.pointerId) {
      const moved =
        pan.moved ||
        Math.abs(event.clientX - pan.anchorClientX) >= MINIMUM_DRAG_PX;
      panRef.current = null;
      setPanning(false);
      if (!moved) onRangeChange(null);
      return;
    }
    const drag = dragRef.current;
    if (drag === null || drag.pointerId !== event.pointerId) return;
    const pointFraction = fractionAt(event);
    const pointTime = domainStart + pointFraction * domainDuration;
    const selected = orderedRange(drag.anchorTime, pointTime);
    setHover({ fraction: pointFraction, eventId: eventIdAt(event.target) });
    dragRef.current = null;
    setDraft(null);
    const click =
      Math.abs(event.clientX - drag.anchorClientX) < MINIMUM_DRAG_PX;
    if (click && drag.eventId !== null) {
      return;
    }
    const minimumSelectionDuration = Math.min(
      domainDuration,
      fullDuration / Math.max(1, spans.length),
    );
    const committedRange =
      selected.end - selected.start < minimumSelectionDuration
        ? centeredRange(
            click ? selected.start : (selected.start + selected.end) / 2,
            minimumSelectionDuration,
            modelStart,
            modelEnd,
          )
        : selected;
    suppressClickRef.current = true;
    onRangeChange(committedRange);
    if (click) {
      const nearest = nearestSpan(spans, selected.start);
      if (nearest !== undefined) onRecordFocus?.(spanPrimaryId(nearest));
    }
  };

  const onPointerCancel = () => {
    dragRef.current = null;
    panRef.current = null;
    setDraft(null);
    setHover(null);
    setPanning(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Escape" || range === null) return;
    event.preventDefault();
    onRangeChange(null);
  };

  const onSpanClick = (eventId: string) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    onRangeChange(null);
    onRecordSelect(eventId);
  };

  const empty = spans.length === 0;
  const selectionStyle =
    visibleRange === null
      ? undefined
      : ({
          "--trajectory-selection-left": `${visibleRange.start * 100}%`,
          "--trajectory-selection-width": `${
            (visibleRange.end - visibleRange.start) * 100
          }%`,
        } as CSSProperties);
  const hoverStyle =
    hover === null
      ? undefined
      : ({
          "--trajectory-hover-left": `${hover.fraction * 100}%`,
        } as CSSProperties);

  return (
    <section
      ref={rootRef}
      className={styles.root}
      aria-label={t("chat.dockTrajectoryTimeline", "Trajectory timeline")}
    >
      <div className={styles.plot}>
        <div className={styles.labels} aria-hidden="true">
          <span>{laneName.input}</span>
          <span>{laneName.model}</span>
          <span>{laneName.tools}</span>
        </div>
        <div
          ref={trackRef}
          className={styles.track}
          role="group"
          tabIndex={0}
          data-panning={panning || undefined}
          aria-label={t("chat.dockTrajectoryTimeline", "Trajectory timeline")}
          style={hoverStyle}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerEnd}
          onPointerCancel={onPointerCancel}
          onKeyDown={onKeyDown}
          onPointerLeave={() => {
            if (dragRef.current === null && panRef.current === null) {
              setHover(null);
            }
          }}
          onDoubleClick={(event) => {
            event.preventDefault();
            onRangeChange(null);
          }}
          onContextMenu={(event) => {
            event.preventDefault();
          }}
        >
          {showsEarlierBoundary ? (
            <EarlierHistoryBoundary
              loading={loadingEarlier}
              onHover={() => {
                setHover(null);
              }}
              onLoad={loadEarlier}
              label={earlierLabel}
            />
          ) : null}
          {hover !== null && hover.eventId === null && draft === null ? (
            <div className={styles.hoverLine} aria-hidden="true" />
          ) : null}
          {visibleRange !== null && selectionStyle !== undefined ? (
            <>
              <div
                className={styles.selection}
                data-dragging={draft !== null || undefined}
                style={selectionStyle}
                aria-hidden="true"
              />
              <div
                className={styles.selectionEdges}
                data-dragging={draft !== null || undefined}
                style={selectionStyle}
                aria-hidden="true"
              />
            </>
          ) : null}
          {empty ? (
            <span className={styles.empty}>
              {t("chat.dockTrajectoryEmpty", "No trajectory events yet")}
            </span>
          ) : (
            <div
              className={styles.lanes}
              data-animate-viewport={animateViewport || undefined}
              style={projectedDomainStyle}
            >
              {spans
                .filter(
                  (span) =>
                    span.eventIds.includes(selectedEventId ?? "") ||
                    (span.end >= domainStart &&
                      span.start <= domainStart + domainDuration),
                )
                .map((span) => {
                  const eventId = spanPrimaryId(span);
                  const current =
                    selectedEventId !== null &&
                    span.eventIds.includes(selectedEventId);
                  const left = ((span.start - modelStart) / fullDuration) * 100;
                  const width = ((span.end - span.start) / fullDuration) * 100;
                  const label = `${laneName[span.lane]}: ${span.kind}`;
                  return (
                    <Tooltip
                      key={span.id}
                      title={label}
                      mouseEnterDelay={TIMELINE_TOOLTIP_DELAY_S}
                    >
                      <button
                        type="button"
                        className={styles.span}
                        data-timeline-span={spanKindAttr(span.kind)}
                        data-lane={span.lane}
                        data-start={span.start}
                        data-end={span.end}
                        data-event-ids={span.eventIds.join(",")}
                        data-error={span.isError || undefined}
                        data-current={current || undefined}
                        data-selected={
                          activeRange === null
                            ? undefined
                            : spanIntersects(span, activeRange)
                            ? "true"
                            : "false"
                        }
                        data-search-match={
                          searchMatchIds === null
                            ? undefined
                            : span.eventIds.some((id) => searchMatchIds.has(id))
                            ? "true"
                            : "false"
                        }
                        data-hovered={
                          hover?.eventId === eventId ? "true" : undefined
                        }
                        aria-pressed={current}
                        aria-label={label}
                        style={
                          {
                            "--trajectory-span-left": `${left}%`,
                            "--trajectory-span-width": `${width}%`,
                            "--trajectory-span-gap": `min(${
                              width * 0.08
                            }%, 1px)`,
                            "--trajectory-span-lane": LANE_INDEX[span.lane],
                          } as CSSProperties
                        }
                        onClick={() => {
                          onSpanClick(eventId);
                        }}
                      />
                    </Tooltip>
                  );
                })}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
