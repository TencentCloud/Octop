import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  trajectoryApi,
  type TrajectoryEvent,
} from "../../../api/modules/trajectory";
import { laneForKind, toLedgerRow } from "../utils/trajectoryModel";
import styles from "./TrajectoryDockPanel.module.less";

interface TrajectoryLedgerProps {
  agentId: string;
  threadId: string;
  events: TrajectoryEvent[];
}

function rowClass(kind: string, isError: boolean, expanded: boolean): string {
  const lane = laneForKind(kind);
  const laneClass =
    lane === "tools"
      ? styles.laneTools
      : lane === "model"
      ? styles.laneModel
      : styles.laneInput;
  return `${styles.row} ${laneClass}${isError ? ` ${styles.rowError}` : ""}${
    expanded ? ` ${styles.rowOpen}` : ""
  }`;
}

function payloadText(payload: Record<string, unknown>): string {
  return JSON.stringify(payload, null, 2);
}

export default function TrajectoryLedger({
  agentId,
  threadId,
  events,
}: TrajectoryLedgerProps) {
  const { t } = useTranslation();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, TrajectoryEvent>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [errorIds, setErrorIds] = useState<Record<string, true>>({});

  const toggle = useCallback(
    async (eventId: string) => {
      if (expandedId === eventId) {
        setExpandedId(null);
        return;
      }
      setExpandedId(eventId);
      if (details[eventId] != null) return;
      setLoadingId(eventId);
      try {
        const detail = await trajectoryApi.event(agentId, threadId, eventId);
        setDetails((prev) => ({ ...prev, [eventId]: detail }));
        setErrorIds((prev) => {
          if (prev[eventId] == null) return prev;
          const next = { ...prev };
          delete next[eventId];
          return next;
        });
      } catch {
        setErrorIds((prev) => ({ ...prev, [eventId]: true }));
      } finally {
        setLoadingId((current) => (current === eventId ? null : current));
      }
    },
    [agentId, details, expandedId, threadId],
  );

  return (
    <ol className={styles.ledger}>
      {events.map((event) => {
        const row = toLedgerRow(event);
        const expanded = expandedId === row.id;
        const detail = details[row.id];
        return (
          <li
            key={row.id}
            className={rowClass(row.kind, row.isError, expanded)}
            data-kind={row.kind}
          >
            <button
              type="button"
              className={styles.rowToggle}
              aria-expanded={expanded}
              onClick={() => void toggle(row.id)}
            >
              <span className={styles.rowTitle}>{row.title}</span>
              {row.summary ? (
                <span className={styles.rowSummary}>{row.summary}</span>
              ) : null}
            </button>
            {expanded ? (
              <pre
                className={styles.rowPayload}
                data-testid="trajectory-payload"
              >
                {loadingId === row.id
                  ? t("chat.dockTrajectoryDetailLoading", "Loading detail…")
                  : errorIds[row.id]
                  ? t(
                      "chat.dockTrajectoryDetailError",
                      "Failed to load event detail",
                    )
                  : payloadText(detail?.payload ?? event.payload)}
              </pre>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
