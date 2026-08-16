import { useMemo, useState } from "react";
import { Input, Popover } from "antd";
import { useTranslation } from "react-i18next";
import { SUBAGENT_EMOJI_OPTIONS } from "../utils/subagentEmojis";
import styles from "./EmojiPicker.module.less";

interface EmojiPickerProps {
  value?: string;
  onChange?: (emoji: string) => void;
  /** Shown when value is empty (subagents default 🤖, skills ✨). */
  fallback?: string;
}

/** Popover grid of catalog emojis for subagent / skill icon selection. */
export default function EmojiPicker({
  value,
  onChange,
  fallback = "🤖",
}: EmojiPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const options = useMemo(() => {
    const q = query.trim();
    if (!q) return SUBAGENT_EMOJI_OPTIONS as readonly string[];
    // Exact / substring match so pasted or partially typed emoji still filters.
    return SUBAGENT_EMOJI_OPTIONS.filter((emoji) => emoji.includes(q));
  }, [query]);

  const current = (value || "").trim() || fallback;

  const panel = (
    <div className={styles.panel}>
      <Input
        allowClear
        size="small"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("common.emojiSearchPlaceholder")}
        aria-label={t("common.emojiSearchPlaceholder")}
        className={styles.search}
      />
      <div
        className={styles.grid}
        role="listbox"
        aria-label={t("common.emojiPickerLabel")}
      >
        {options.map((emoji) => {
          const active = emoji === current;
          return (
            <button
              key={emoji}
              type="button"
              role="option"
              aria-selected={active}
              aria-label={emoji}
              className={`${styles.option} ${active ? styles.active : ""}`}
              onClick={() => {
                onChange?.(emoji);
                setOpen(false);
                setQuery("");
              }}
            >
              <span aria-hidden>{emoji}</span>
            </button>
          );
        })}
        {options.length === 0 ? (
          <div className={styles.empty}>{t("common.emojiNoResults")}</div>
        ) : null}
      </div>
    </div>
  );

  return (
    <Popover
      trigger="click"
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
      content={panel}
      placement="bottomLeft"
      arrow={false}
      overlayClassName={styles.overlay}
    >
      <button
        type="button"
        className={styles.trigger}
        aria-label={t("common.emojiPickerLabel")}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={styles.triggerEmoji} aria-hidden>
          {current}
        </span>
        <span className={styles.triggerHint}>{t("common.emojiPick")}</span>
      </button>
    </Popover>
  );
}
