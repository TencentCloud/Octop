import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldAlert, ShieldOff } from "lucide-react";
import { Popover, Tooltip } from "antd";
import cx from "classnames";
import type { HitlSessionPolicy } from "../utils/hitlSessionPolicy";
import styles from "../index.module.less";

interface ManagedApprovalPickerProps {
  policy: HitlSessionPolicy;
  onChange: (policy: HitlSessionPolicy) => void;
  disabled?: boolean;
  disabledHint?: string;
}

/** Approval switch for a chat whose replies come from an external agent. */
export default function ManagedApprovalPicker({
  policy,
  onChange,
  disabled = false,
  disabledHint,
}: ManagedApprovalPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const yolo = policy.mode === "allow_all";
  const triggerLabel = yolo
    ? t("chat.managedApproval.yolo")
    : t("chat.managedApproval.ask");

  const choose = (next: HitlSessionPolicy) => {
    onChange(next);
    setOpen(false);
  };

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
              !yolo && styles.modeMenuItemActive,
            )}
            onClick={() => choose({ mode: "ask" })}
          >
            <span className={styles.modeMenuTitle}>
              <ShieldAlert size={16} />
              {t("chat.managedApproval.ask")}
            </span>
            <span className={styles.modeMenuHint}>
              {t("chat.managedApproval.askHint")}
            </span>
          </button>
          <button
            type="button"
            className={cx(
              styles.modeMenuItem,
              yolo && styles.modeMenuItemActive,
            )}
            onClick={() => choose({ mode: "allow_all" })}
          >
            <span className={styles.modeMenuTitle}>
              <ShieldOff size={16} />
              {t("chat.managedApproval.yolo")}
            </span>
            <span className={styles.modeMenuHint}>
              {t("chat.managedApproval.yoloHint")}
            </span>
          </button>
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
            yolo && styles.secondaryBtnModelActive,
          )}
          type="button"
          aria-label={`${t("chat.managedApproval.picker")}: ${triggerLabel}`}
          data-testid="managed-approval-picker"
        >
          {yolo ? <ShieldOff size={16} /> : <ShieldAlert size={16} />}
        </button>
      </Tooltip>
    </Popover>
  );
}
