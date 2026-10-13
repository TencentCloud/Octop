import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

interface ScrollToBottomButtonProps {
  visible: boolean;
  onClick: () => void;
  /** Live generation below the fold — emphasize "new replies". */
  hasNewActivity?: boolean;
}

export default function ScrollToBottomButton({
  visible,
  onClick,
  hasNewActivity = false,
}: ScrollToBottomButtonProps) {
  const { t } = useTranslation();
  const label = hasNewActivity
    ? t("chat.newRepliesBelow", { defaultValue: "有新回复" })
    : t("chat.scrollToBottom");
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [overlapsTool, setOverlapsTool] = useState(false);

  useEffect(() => {
    if (!visible) return;

    const button = buttonRef.current;
    const wrapper = button?.closest(`.${styles.messageListWrapper}`);
    const scroller = wrapper?.querySelector(`.${styles.messageList}`);
    if (!button || !wrapper || !scroller) return;

    let frame = 0;
    const updateOverlap = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const buttonRect = button.getBoundingClientRect();
        const toolRenderers = wrapper.querySelectorAll<HTMLElement>(
          "[data-octop-tool-renderer]",
        );
        const overlaps = Array.from(toolRenderers).some((tool) => {
          const toolRect = tool.getBoundingClientRect();
          return (
            buttonRect.left < toolRect.right &&
            buttonRect.right > toolRect.left &&
            buttonRect.top < toolRect.bottom &&
            buttonRect.bottom > toolRect.top
          );
        });
        setOverlapsTool(overlaps);
      });
    };

    updateOverlap();
    scroller.addEventListener("scroll", updateOverlap, { passive: true });
    window.addEventListener("resize", updateOverlap);

    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(updateOverlap);
    resizeObserver?.observe(wrapper);
    wrapper
      .querySelectorAll<HTMLElement>("[data-octop-tool-renderer]")
      .forEach((tool) => resizeObserver?.observe(tool));

    return () => {
      cancelAnimationFrame(frame);
      scroller.removeEventListener("scroll", updateOverlap);
      window.removeEventListener("resize", updateOverlap);
      resizeObserver?.disconnect();
    };
  }, [visible, hasNewActivity]);

  const actuallyVisible = visible && !overlapsTool;
  return (
    <button
      ref={buttonRef}
      className={`${styles.scrollToBottomBtn} ${
        actuallyVisible
          ? styles.scrollToBottomBtnVisible
          : styles.scrollToBottomBtnHidden
      }${
        hasNewActivity && actuallyVisible
          ? ` ${styles.scrollToBottomBtnHasNew}`
          : ""
      }`}
      onClick={onClick}
      type="button"
      title={label}
      aria-label={label}
      aria-hidden={!actuallyVisible}
      tabIndex={actuallyVisible ? 0 : -1}
    >
      <ChevronDown size={14} strokeWidth={2} aria-hidden />
      <span>{label}</span>
    </button>
  );
}
