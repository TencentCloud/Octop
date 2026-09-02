import { Fragment } from "react";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import { laneForKind, toLedgerRow } from "../utils/trajectoryModel";
import styles from "./TrajectoryDockPanel.module.less";

export interface TrajectoryLedgerProps {
  events: TrajectoryEvent[];
  selectedEventId: string | null;
  onSelect: (eventId: string) => void;
  focusEventIds: ReadonlySet<string> | null;
  searchMatchIds: ReadonlySet<string> | null;
}

function rowClass(kind: string, isError: boolean, selected: boolean): string {
  const lane = laneForKind(kind);
  const laneClass =
    lane === "tools"
      ? styles.laneTools
      : lane === "model"
      ? styles.laneModel
      : styles.laneInput;
  return `${styles.row} ${laneClass}${isError ? ` ${styles.rowError}` : ""}${
    selected ? ` ${styles.rowSelected}` : ""
  }`;
}

function matchAttr(
  ids: ReadonlySet<string> | null,
  eventId: string,
): "true" | "false" | undefined {
  if (ids == null) return undefined;
  return ids.has(eventId) ? "true" : "false";
}

export default function TrajectoryLedger({
  events,
  selectedEventId,
  onSelect,
  focusEventIds,
  searchMatchIds,
}: TrajectoryLedgerProps) {
  return (
    <ol className={styles.ledger}>
      {events.map((event, index) => {
        const row = toLedgerRow(event);
        const selected = selectedEventId === row.id;
        const prevTurn = events[index - 1]?.turn_id;
        const showTurnHeader =
          event.turn_id != null && event.turn_id !== prevTurn;
        return (
          <Fragment key={row.id}>
            {showTurnHeader ? (
              <li
                className={styles.turnHeader}
                data-testid="trajectory-turn-header"
              >
                {event.turn_id}
              </li>
            ) : null}
            <li
              className={rowClass(row.kind, row.isError, selected)}
              data-kind={row.kind}
              data-focus-match={matchAttr(focusEventIds, row.id)}
              data-search-match={matchAttr(searchMatchIds, row.id)}
            >
              <button
                type="button"
                className={styles.rowToggle}
                aria-selected={selected}
                onClick={() => onSelect(row.id)}
              >
                <span className={styles.rowTitle}>{row.title}</span>
                {row.summary ? (
                  <span className={styles.rowSummary}>{row.summary}</span>
                ) : null}
              </button>
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}
