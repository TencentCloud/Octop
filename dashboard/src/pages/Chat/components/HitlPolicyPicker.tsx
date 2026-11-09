import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldAlert, ShieldCheck, X } from "lucide-react";
import { Popover, Tooltip } from "antd";
import cx from "classnames";
import { useToolDisplayNames } from "../hooks/toolDisplayNames";
import {
  isHitlBypassPolicy,
  withoutAllowTools,
  type HitlSessionPolicy,
} from "../utils/hitlSessionPolicy";
import styles from "../index.module.less";

interface HitlPolicyPickerProps {
  policy: HitlSessionPolicy;
  onChange: (policy: HitlSessionPolicy) => void;
  disabled?: boolean;
  disabledHint?: string;
}

export default function HitlPolicyPicker({
  policy,
  onChange,
  disabled = false,
  disabledHint,
}: HitlPolicyPickerProps) {
  const { t } = useTranslation();
  const toolLabelOf = useToolDisplayNames();
  const [open, setOpen] = useState(false);
  const bypass = isHitlBypassPolicy(policy);
  const toolNames = policy.mode === "allow_tools" ? policy.tools ?? [] : [];
  const triggerLabel =
    policy.mode === "allow_all"
      ? t("chat.hitl.policy.allowAll")
      : policy.mode === "allow_tools"
      ? t("chat.hitl.policy.allowToolsCount", { count: toolNames.length })
      : t("chat.hitl.policy.ask");

  return (
    <Popover
      trigger="click"
      placement="topLeft"
      open={disabled ? false : open}
      onOpenChange={disabled ? undefined : setOpen}
      overlayClassName={styles.modelPopover}
      content={
        <div className={styles.modeMenu}>
          <button
            type="button"
            className={cx(
              styles.modeMenuItem,
              policy.mode === "ask" && styles.modeMenuItemActive,
            )}
            onClick={() => {
              onChange({ mode: "ask" });
              setOpen(false);
            }}
          >
            <span className={styles.modeMenuTitle}>
              <ShieldAlert size={16} />
              {t("chat.hitl.policy.ask")}
            </span>
            <span className={styles.modeMenuHint}>
              {t("chat.hitl.policy.askHint")}
            </span>
          </button>
          <button
            type="button"
            className={cx(
              styles.modeMenuItem,
              policy.mode === "allow_all" && styles.modeMenuItemActive,
            )}
            onClick={() => {
              onChange({ mode: "allow_all" });
              setOpen(false);
            }}
          >
            <span className={styles.modeMenuTitle}>
              <ShieldCheck size={16} />
              {t("chat.hitl.policy.allowAll")}
            </span>
            <span className={styles.modeMenuHint}>
              {t("chat.hitl.policy.allowAllHint")}
            </span>
          </button>
          {toolNames.length > 0 ? (
            <div className={styles.modeMenuTools}>
              <div className={styles.modeMenuToolsLabel}>
                {t("chat.hitl.policy.allowedTools")}
              </div>
              {toolNames.map((name) => {
                const label = toolLabelOf(name) || name;
                return (
                  <div key={name} className={styles.modeMenuToolRow}>
                    <span className={styles.modeMenuToolName}>{label}</span>
                    <button
                      type="button"
                      className={styles.modeMenuToolRemove}
                      aria-label={t("chat.hitl.policy.removeTool", {
                        tool: label,
                      })}
                      onClick={() => onChange(withoutAllowTools(policy, name))}
                    >
                      <X size={14} />
                    </button>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      }
    >
      <Tooltip
        title={disabled ? disabledHint || triggerLabel : triggerLabel}
        mouseEnterDelay={0.4}
      >
        <button
          className={cx(
            styles.secondaryBtn,
            bypass && styles.secondaryBtnModelActive,
          )}
          type="button"
          aria-label={`${t("chat.hitl.policy.picker")}: ${triggerLabel}`}
          data-testid="hitl-policy-picker"
        >
          {policy.mode === "ask" ? (
            <ShieldAlert size={16} />
          ) : (
            <ShieldCheck size={16} />
          )}
        </button>
      </Tooltip>
    </Popover>
  );
}
