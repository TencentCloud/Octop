import {
  Hammer,
  ListTodo,
  MessageCircleQuestion,
  ShieldOff,
  type LucideIcon,
} from "lucide-react";
import cx from "classnames";
import {
  acpSessionModeText,
  isUnattendedSessionMode,
  type AcpSessionMode,
} from "../../../api/modules/acp";
import styles from "../index.module.less";

export function sessionModeIcon(modeId: string): LucideIcon {
  const folded = modeId.toLowerCase();
  if (isUnattendedSessionMode(modeId)) {
    return ShieldOff;
  }
  if (folded.includes("plan")) return ListTodo;
  if (
    folded.includes("read-only") ||
    folded.includes("readonly") ||
    folded === "default" ||
    folded.includes("ask")
  ) {
    return MessageCircleQuestion;
  }
  return Hammer;
}

export function SessionModeMenu({
  modes,
  modeId,
  language,
  onChange,
}: {
  modes: AcpSessionMode[];
  modeId: string;
  language: string;
  onChange: (modeId: string) => void;
}) {
  return (
    <div className={styles.modeMenu}>
      {modes.map((mode) => {
        const Icon = sessionModeIcon(mode.id);
        return (
          <button
            key={mode.id}
            type="button"
            className={cx(
              styles.modeMenuItem,
              modeId === mode.id && styles.modeMenuItemActive,
            )}
            onClick={() => onChange(mode.id)}
          >
            <span className={styles.modeMenuTitle}>
              <Icon size={16} />
              {acpSessionModeText(mode, language, "name")}
            </span>
            <span className={styles.modeMenuHint}>
              {acpSessionModeText(mode, language, "hint")}
            </span>
          </button>
        );
      })}
    </div>
  );
}
