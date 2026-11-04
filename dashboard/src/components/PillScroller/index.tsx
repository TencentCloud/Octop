import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import cx from "classnames";
import styles from "./index.module.less";

export interface PillOption {
  value: string;
  label: string;
}

function ScrollArrow({
  show,
  side,
  label,
  onClick,
}: {
  show: boolean;
  side: "prev" | "next";
  label: string;
  onClick: () => void;
}) {
  return (
    <AnimatePresence initial={false}>
      {show ? (
        <motion.button
          key={side}
          type="button"
          className={cx(
            styles.arrow,
            side === "prev" ? styles.arrowPrev : styles.arrowNext,
          )}
          aria-label={label}
          initial={false}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={onClick}
        >
          <span className={styles.arrowIcon}>
            {side === "prev" ? (
              <ChevronLeft size={14} />
            ) : (
              <ChevronRight size={14} />
            )}
          </span>
        </motion.button>
      ) : null}
    </AnimatePresence>
  );
}

/** One-row pills that scroll with the trackpad, a drag, or the end arrows. */
export default function PillScroller({
  options,
  active,
  onSelect,
  prevLabel,
  nextLabel,
  className,
}: {
  options: PillOption[];
  active: string;
  onSelect: (value: string) => void;
  prevLabel: string;
  nextLabel: string;
  className?: string;
}) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef({
    pointerId: -1,
    startX: 0,
    startScroll: 0,
    moved: false,
  });
  const [edges, setEdges] = useState({ left: false, right: false });

  const updateEdges = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    const left = el.scrollLeft > 2;
    const right = max - el.scrollLeft > 2;
    setEdges((prev) =>
      prev.left === left && prev.right === right ? prev : { left, right },
    );
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    updateEdges();
    el.addEventListener("scroll", updateEdges, { passive: true });
    const observer = new ResizeObserver(updateEdges);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", updateEdges);
      observer.disconnect();
    };
  }, [options, updateEdges]);

  const scrollByDir = (dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({
      left: dir * Math.max(160, Math.round(el.clientWidth * 0.7)),
      behavior: "smooth",
    });
  };

  return (
    <div className={cx(styles.scroller, className)}>
      <ScrollArrow
        show={edges.left}
        side="prev"
        label={prevLabel}
        onClick={() => scrollByDir(-1)}
      />
      <div
        ref={scrollerRef}
        className={styles.track}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          const el = scrollerRef.current;
          if (!el || el.scrollWidth <= el.clientWidth + 1) return;
          // Capture only after the pointer actually drags. Capturing on
          // pointerdown retargets the click away from the pill.
          dragRef.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startScroll: el.scrollLeft,
            moved: false,
          };
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current;
          if (drag.pointerId !== event.pointerId) return;
          const el = scrollerRef.current;
          if (!el) return;
          const dx = event.clientX - drag.startX;
          if (!drag.moved) {
            if (Math.abs(dx) <= 6) return;
            drag.moved = true;
            el.setPointerCapture(event.pointerId);
          }
          el.scrollLeft = drag.startScroll - dx;
        }}
        onPointerUp={(event) => {
          if (dragRef.current.pointerId !== event.pointerId) return;
          dragRef.current.pointerId = -1;
        }}
        onPointerCancel={() => {
          dragRef.current.pointerId = -1;
          dragRef.current.moved = false;
        }}
        onClickCapture={(event) => {
          if (!dragRef.current.moved) return;
          dragRef.current.moved = false;
          event.preventDefault();
          event.stopPropagation();
        }}
      >
        {options.map((opt) => {
          const selected = active === opt.value;
          return (
            <button
              key={opt.value || "__all"}
              type="button"
              aria-pressed={selected}
              className={cx(styles.pill, selected && styles.pillActive)}
              onClick={() => onSelect(opt.value)}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <ScrollArrow
        show={edges.right}
        side="next"
        label={nextLabel}
        onClick={() => scrollByDir(1)}
      />
    </div>
  );
}
