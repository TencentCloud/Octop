import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import { laneForKind, toLedgerRow } from "../utils/trajectoryModel";
import styles from "./TrajectoryDockPanel.module.less";

interface TrajectoryLedgerProps {
  events: TrajectoryEvent[];
}

function rowClass(kind: string, isError: boolean): string {
  const lane = laneForKind(kind);
  const laneClass =
    lane === "tools"
      ? styles.laneTools
      : lane === "model"
      ? styles.laneModel
      : styles.laneInput;
  return `${styles.row} ${laneClass}${isError ? ` ${styles.rowError}` : ""}`;
}

export default function TrajectoryLedger({ events }: TrajectoryLedgerProps) {
  return (
    <ol className={styles.ledger}>
      {events.map((event) => {
        const row = toLedgerRow(event);
        return (
          <li
            key={row.id}
            className={rowClass(row.kind, row.isError)}
            data-kind={row.kind}
          >
            <span className={styles.rowTitle}>{row.title}</span>
            {row.summary ? (
              <span className={styles.rowSummary}>{row.summary}</span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
