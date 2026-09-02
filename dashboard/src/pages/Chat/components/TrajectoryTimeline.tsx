import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import type { TrajectoryLane } from "../utils/trajectoryModel";
import {
  deriveSwimlaneSpans,
  type SwimlaneMode,
  type SwimlaneSpan,
} from "../utils/trajectoryTimeline";
import styles from "./TrajectoryTimeline.module.less";

const LANES: TrajectoryLane[] = ["input", "model", "tools"];

interface TrajectoryTimelineProps {
  events: TrajectoryEvent[];
  mode: SwimlaneMode;
  focusedSpanId?: string | null;
  onFocusSpan?: (span: SwimlaneSpan | null) => void;
}

function spanClass(lane: TrajectoryLane, focused: boolean): string {
  const laneClass =
    lane === "tools"
      ? styles.spanTools
      : lane === "model"
      ? styles.spanModel
      : styles.spanInput;
  return `${styles.span} ${laneClass}${
    focused ? ` ${styles.spanFocused}` : ""
  }`;
}

export default function TrajectoryTimeline({
  events,
  mode,
  focusedSpanId = null,
  onFocusSpan,
}: TrajectoryTimelineProps) {
  const { t } = useTranslation();
  const spans = useMemo(
    () => deriveSwimlaneSpans(events, mode),
    [events, mode],
  );
  const extent = spans.reduce((max, span) => Math.max(max, span.end), 1);

  const laneName = (lane: TrajectoryLane): string => {
    if (lane === "input") {
      return t("chat.dockTrajectoryLaneInput", "Input");
    }
    if (lane === "model") {
      return t("chat.dockTrajectoryLaneModel", "Model");
    }
    return t("chat.dockTrajectoryLaneTools", "Tools");
  };

  return (
    <div
      className={styles.root}
      role="group"
      aria-label={t("chat.dockTrajectoryTimeline", "Trajectory timeline")}
    >
      {LANES.map((lane) => (
        <div key={lane} className={styles.lane} data-lane={lane}>
          <span className={styles.laneLabel}>{laneName(lane)}</span>
          <div className={styles.track}>
            {spans
              .filter((span) => span.lane === lane)
              .map((span) => {
                const focused = focusedSpanId === span.id;
                const width = ((span.end - span.start) / extent) * 100;
                return (
                  <button
                    key={span.id}
                    type="button"
                    className={spanClass(lane, focused)}
                    data-lane={lane}
                    data-start={span.start}
                    data-end={span.end}
                    data-event-ids={span.eventIds.join(",")}
                    aria-pressed={focused}
                    aria-label={laneName(lane)}
                    style={{
                      left: `${(span.start / extent) * 100}%`,
                      width: `${width}%`,
                    }}
                    onClick={() => {
                      if (!onFocusSpan) return;
                      onFocusSpan(focused ? null : span);
                    }}
                  />
                );
              })}
          </div>
        </div>
      ))}
    </div>
  );
}
