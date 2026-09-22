import { ChevronDown, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Dropdown } from "antd";
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
}: HitlApprovalCardProps) {
  const { t } = useTranslation();
  const toolLabelOf = useToolDisplayNames();
  const interactive = status === "pending" && Boolean(onDecision);
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
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                { key: "allow_tools", label: allowToolsLabel },
                {
                  key: "allow_all",
                  label: t("chat.hitl.allowAll", "Allow all for this chat"),
                },
              ],
              onClick: ({ key }) => {
                if (key === "allow_all") {
                  onDecision?.(
                    actions.map(() => ({ type: "approve" })),
                    { mode: "allow_all" },
                  );
                  return;
                }
                onDecision?.(
                  actions.map(() => ({ type: "approve" })),
                  { mode: "allow_tools", tools: toolNames },
                );
              },
            }}
          >
            <button
              type="button"
              className={`${styles.actionButton} ${styles.secondaryAction}`}
            >
              {t("chat.hitl.allowMenu", "Allow")}
              <ChevronDown size={14} />
            </button>
          </Dropdown>
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
          {resolvedLabel}
        </div>
      ) : null}
    </div>
  );
}
