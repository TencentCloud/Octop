import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import type { HitlActionRequest } from "../../../api/types/hitl";
import { useToolDisplayNames } from "../hooks/toolDisplayNames";
import type { HitlRequestResolution } from "../hooks/sseHelpers";
import type { HitlDecisionHandler } from "../utils/hitlSessionPolicy";
import {
  summarizeHitlAction,
  type HitlTranslate,
} from "../utils/summarizeHitlAction";
import styles from "./HitlApprovalCard.module.less";

export interface HitlApprovalCardProps {
  actions: HitlActionRequest[];
  status: "pending" | "approved" | "rejected";
  resolution?: HitlRequestResolution;
  onDecision?: HitlDecisionHandler;
  pendingId?: string;
  /** Team member who asked for this approval. */
  speakerName?: string;
}

function uniqueToolNames(actions: HitlActionRequest[]): string[] {
  return [
    ...new Set(
      actions
        .map((action) => action.name.trim())
        .filter((name) => name.length > 0),
    ),
  ];
}

export default function HitlApprovalCard({
  actions,
  status,
  resolution,
  onDecision,
  pendingId,
  speakerName,
}: HitlApprovalCardProps) {
  const { t } = useTranslation();
  const toolLabelOf = useToolDisplayNames();
  const interactive = status === "pending" && Boolean(onDecision);
  const emit = (
    decisions: Array<{ type: string; message?: string }>,
    policy?: Parameters<NonNullable<HitlDecisionHandler>>[1],
  ) => {
    if (pendingId) onDecision?.(decisions, policy, pendingId);
    else if (policy) onDecision?.(decisions, policy);
    else onDecision?.(decisions);
  };
  const toolNames = uniqueToolNames(actions);
  const allowToolsLabel =
    toolNames.length > 1
      ? t("chat.hitl.allowTools", "Allow these tools for this chat")
      : t("chat.hitl.allowTool", "Allow this tool for this chat");

  const resolvedLabel =
    status === "rejected"
      ? t("chat.hitl.rejectedLabel", "Rejected")
      : resolution === "allow_all"
      ? t("chat.hitl.allowedAll", "Allowed all for this chat")
      : resolution === "allow_tool"
      ? toolNames.length > 1
        ? t("chat.hitl.allowedTools", "Allowed these tools for this chat")
        : t("chat.hitl.allowedTool", "Allowed this tool for this chat")
      : t("chat.hitl.approved", "Approved");

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
      {speakerName ? (
        <p className={styles.member}>
          {t("chat.hitl.memberRequest", {
            name: speakerName,
            defaultValue: "{{name}} is asking to run this",
          })}
        </p>
      ) : null}
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
        <>
          <div className={styles.actions}>
            <button
              type="button"
              className={cx(styles.actionButton, styles.primaryAction)}
              onClick={() => emit(actions.map(() => ({ type: "approve" })))}
            >
              {t("chat.hitl.approve", "Approve")}
            </button>
            <button
              type="button"
              className={cx(styles.actionButton, styles.secondaryAction)}
              title={allowToolsLabel}
              onClick={() =>
                emit(
                  actions.map(() => ({ type: "approve" })),
                  {
                    mode: "allow_tools",
                    tools: toolNames,
                  },
                )
              }
            >
              {t("chat.hitl.allowSession", "Allow for this chat")}
            </button>
            <button
              type="button"
              className={cx(styles.actionButton, styles.dangerAction)}
              onClick={() =>
                emit(
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
          <button
            type="button"
            className={styles.allowAllLink}
            onClick={() =>
              emit(
                actions.map(() => ({ type: "approve" })),
                {
                  mode: "allow_all",
                },
              )
            }
          >
            {t("chat.hitl.allowAllLink", "Allow all tools in this chat")}
          </button>
        </>
      ) : status !== "pending" ? (
        <div
          className={cx(
            styles.resolved,
            status === "approved" ? styles.approved : styles.rejected,
          )}
        >
          {resolvedLabel}
        </div>
      ) : null}
    </div>
  );
}
