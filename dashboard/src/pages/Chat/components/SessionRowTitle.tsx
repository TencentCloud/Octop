import { memo, useCallback, useEffect, useRef, useState } from "react";
import styles from "../index.module.less";

/** Gap between duplicated title copies for seamless loop. */
const MARQUEE_GAP_PX = 24;

interface SessionRowTitleProps {
  text: string;
  className?: string;
  /** When set, defers hover detection to the parent row. */
  hovered?: boolean;
}

/** Truncated session title; scrolls horizontally on hover when text overflows. */
export const SessionRowTitle = memo(function SessionRowTitle({
  text,
  className,
  hovered: hoveredProp,
}: SessionRowTitleProps) {
  const wrapRef = useRef<HTMLSpanElement>(null);
  const innerRef = useRef<HTMLSpanElement>(null);
  const [overflows, setOverflows] = useState(false);
  const [scrollPx, setScrollPx] = useState(0);
  const [textWidth, setTextWidth] = useState(0);
  const [localHovered, setLocalHovered] = useState(false);
  const hovered = hoveredProp ?? localHovered;

  const measure = useCallback(() => {
    const wrap = wrapRef.current;
    const inner = innerRef.current;
    if (!wrap || !inner) return;
    const tw = inner.scrollWidth;
    const delta = tw - wrap.clientWidth;
    const doesOverflow = delta > 1;
    setOverflows(doesOverflow);
    setScrollPx(doesOverflow ? delta : 0);
    setTextWidth(tw);
  }, [text]);

  const scrolling = hovered && overflows && scrollPx > 0;
  const marqueeShift = textWidth + MARQUEE_GAP_PX;
  const duration = marqueeShift > 0 ? Math.max(4, marqueeShift / 40) : 4;

  useEffect(() => {
    if (scrolling) return;
    measure();
    const wrap = wrapRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [measure, scrolling]);

  return (
    <span
      ref={wrapRef}
      className={className}
      onMouseEnter={
        hoveredProp === undefined ? () => setLocalHovered(true) : undefined
      }
      onMouseLeave={
        hoveredProp === undefined ? () => setLocalHovered(false) : undefined
      }
      title={overflows && !hovered ? text : undefined}
    >
      <span
        ref={innerRef}
        className={
          scrolling
            ? styles.sessionRowTitleInnerScroll
            : styles.sessionRowTitleInner
        }
        style={
          scrolling
            ? ({
                animationDuration: `${duration}s`,
                ["--marquee-shift" as string]: `-${marqueeShift}px`,
                ["--title-scroll" as string]: `-${scrollPx}px`,
              } as React.CSSProperties)
            : undefined
        }
      >
        {scrolling ? (
          <>
            <span>{text}</span>
            <span className={styles.sessionRowTitleMarqueeCopy} aria-hidden>
              {text}
            </span>
          </>
        ) : (
          text
        )}
      </span>
    </span>
  );
});
