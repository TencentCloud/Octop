import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { HitlActionRequest } from "../../../api/types/hitl";
import { useToolDisplayNames } from "../hooks/toolDisplayNames";
import {
  summarizeHitlAction,
  type HitlTranslate,
} from "../utils/summarizeHitlAction";
import styles from "./HitlApprovalCard.module.less";

export interface HitlApprovalCardProps {
  actions: HitlActionRequest[];
  status: "pending" | "approved" | "rejected";
  onDecision?: (decisions: Array<{ type: string; message?: string }>) => void;
}

export default function HitlApprovalCard({
  actions,
  status,
  onDecision,
}: HitlApprovalCardProps) {
  const { t } = useTranslation();
  const toolLabelOf = useToolDisplayNames();
  const interactive = status === "pending" && Boolean(onDecision);

  return (
    <div className={styles.card} role="status">
      <div className={styles.titleRow}>
        <span className={styles.iconWrap} aria-hidden="true">
          <ShieldAlert size={18} strokeWidth={2} />
        </span>
        <div className={styles.title}>
          {t("chat.hitl.title", "Confirm this action")}
        </div>
      </div>
      {actions.map((action, idx) => {
        const view = summarizeHitlAction(
          action.name,
          action.args,
          t as HitlTranslate,
          toolLabelOf(action.name),
          action.description,
        );
        return (
          <div key={`${action.name}-${idx}`} className={styles.action}>
            <div className={styles.toolName}>{view.toolLabel}</div>
            {view.summary && view.summary !== view.toolLabel ? (
              <p className={styles.summary}>{view.summary}</p>
            ) : null}
            {view.rows.length > 0 ? (
              <dl className={styles.rows}>
                {view.rows.map((row, rowIdx) => (
                  <div key={`${row.label}-${rowIdx}`} className={styles.row}>
                    <dt>{row.label}</dt>
                    <dd className={row.mono ? styles.mono : undefined}>
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </div>
        );
      })}
      {interactive ? (
        <div className={styles.actions}>
          <button
            type="button"
            className={`${styles.actionButton} ${styles.primaryAction}`}
            onClick={() =>
              onDecision?.(actions.map(() => ({ type: "approve" })))
            }
          >
            {t("chat.hitl.approve", "Approve")}
          </button>
          <button
            type="button"
            className={`${styles.actionButton} ${styles.dangerAction}`}
            onClick={() =>
              onDecision?.(
                actions.map(() => ({
                  type: "reject",
                  message: t("chat.hitl.rejected", "Rejected by user"),
                })),
              )
            }
          >
            {t("chat.hitl.reject", "Reject")}
          </button>
        </div>
      ) : status !== "pending" ? (
        <div
          className={`${styles.resolved} ${
            status === "approved" ? styles.approved : styles.rejected
          }`}
        >
          {status === "approved"
            ? t("chat.hitl.approved", "Approved")
            : t("chat.hitl.rejectedLabel", "Rejected")}
        </div>
      ) : null}
    </div>
  );
}
