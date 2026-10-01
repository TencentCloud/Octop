import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Hammer,
  ListTodo,
  MessageCircleQuestion,
  type LucideIcon,
} from "lucide-react";
import { Popover, Tooltip } from "antd";
import type { ConversationMode } from "../utils/conversationMode";
import styles from "../index.module.less";

const MODE_OPTIONS: readonly {
  mode: ConversationMode;
  Icon: LucideIcon;
  hintKey: string;
}[] = [
  {
    mode: "craft",
    Icon: Hammer,
    hintKey: "chat.conversationMode.craftHint",
  },
  {
    mode: "plan",
    Icon: ListTodo,
    hintKey: "chat.conversationMode.planHint",
  },
  {
    mode: "ask",
    Icon: MessageCircleQuestion,
    hintKey: "chat.conversationMode.askHint",
  },
];

function ModeGlyph({ mode }: { mode: ConversationMode }) {
  const Icon = MODE_OPTIONS.find((item) => item.mode === mode)?.Icon ?? Hammer;
  return <Icon size={16} />;
}

interface ConversationModePickerProps {
  conversationMode: ConversationMode;
  onChange: (mode: ConversationMode) => void;
}

export default function ConversationModePicker({
  conversationMode,
  onChange,
}: ConversationModePickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const modeLabel = t(`chat.conversationMode.${conversationMode}`);

  return (
    <Popover
      trigger="click"
      placement="topLeft"
      open={open}
      onOpenChange={setOpen}
      overlayClassName={styles.modelPopover}
      content={
        <div className={styles.modeMenu}>
          {MODE_OPTIONS.map(({ mode, Icon, hintKey }) => (
            <button
              key={mode}
              type="button"
              className={`${styles.modeMenuItem} ${
                conversationMode === mode ? styles.modeMenuItemActive : ""
              }`}
              onClick={() => {
                onChange(mode);
                setOpen(false);
              }}
            >
              <span className={styles.modeMenuTitle}>
                <Icon size={16} />
                {t(`chat.conversationMode.${mode}`)}
              </span>
              <span className={styles.modeMenuHint}>{t(hintKey)}</span>
            </button>
          ))}
        </div>
      }
    >
      <Tooltip title={modeLabel} mouseEnterDelay={0.4}>
        <button
          className={`${styles.secondaryBtn} ${
            conversationMode !== "craft" ? styles.secondaryBtnModelActive : ""
          }`}
          type="button"
          aria-label={`${t("chat.conversationMode.picker")}: ${modeLabel}`}
          data-testid="conversation-mode-picker"
        >
          <ModeGlyph mode={conversationMode} />
        </button>
      </Tooltip>
    </Popover>
  );
}
