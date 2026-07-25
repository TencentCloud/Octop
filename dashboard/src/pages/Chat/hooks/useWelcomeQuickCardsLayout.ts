import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useIsMobile } from "../../../hooks/useIsMobile";
import type { WelcomeQuickCard } from "../components/WelcomeScreen";

const MAX_DEFAULT_ROWS = 2;
const MOBILE_MIN_VISIBLE = 2;
const MASCOT_ASPECT = 711 / 812;
const HEADING_HEIGHT_NO_MASCOT = 72;

function estimateMascotHeight(): number {
  const w = window.innerWidth;
  if (w < 768) return Math.round(185 * MASCOT_ASPECT - 14);
  if (w >= 1200) return Math.round(300 * MASCOT_ASPECT - 24);
  return Math.round(240 * MASCOT_ASPECT - 20);
}

export function useWelcomeQuickCardsLayout(quickCards: WelcomeQuickCard[]) {
  const isMobile = useIsMobile();
  const welcomeRef = useRef<HTMLDivElement | null>(null);
  const headingRef = useRef<HTMLDivElement | null>(null);
  const sectionTitleRef = useRef<HTMLSpanElement | null>(null);
  const probeRef = useRef<HTMLDivElement | null>(null);
  const [defaultVisible, setDefaultVisible] = useState<number>(
    quickCards.length,
  );
  const [expanded, setExpanded] = useState(false);
  // Keep mascot visible — auto-hiding on ResizeObserver/viewport changes caused
  // Safari welcome-screen flicker (animated assets + layout thrash).
  const autoHideMascot = false;

  useEffect(() => {
    setExpanded(false);
    setDefaultVisible(quickCards.length);
  }, [quickCards.length]);

  useLayoutEffect(() => {
    const compute = () => {
      const w = window.innerWidth;
      const cols = w < 480 ? 1 : w < 768 ? 2 : w < 1200 ? 2 : 3;
      const maxByRows = MAX_DEFAULT_ROWS * cols;

      if (!isMobile) {
        setDefaultVisible((prev) => {
          const next = Math.min(quickCards.length, maxByRows);
          return prev === next ? prev : next;
        });
        return;
      }

      const container = welcomeRef.current;
      const probe = probeRef.current;
      if (!container || !probe || quickCards.length === 0) {
        setDefaultVisible((prev) => {
          const next = Math.max(
            MOBILE_MIN_VISIBLE,
            Math.min(quickCards.length, maxByRows),
          );
          return prev === next ? prev : next;
        });
        return;
      }

      const containerRect = container.getBoundingClientRect();
      const sectionTitleHeight =
        sectionTitleRef.current?.getBoundingClientRect().height ?? 0;
      const headingHeight = HEADING_HEIGHT_NO_MASCOT + estimateMascotHeight();
      const cardHeight = probe.getBoundingClientRect().height;
      if (cardHeight <= 0) return;

      const reserved = 18 + 36 + 24;
      const available =
        containerRect.height - headingHeight - sectionTitleHeight - reserved;
      const rowGap = 8;
      const rowsFit = Math.max(
        1,
        Math.floor((available + rowGap) / (cardHeight + rowGap)),
      );
      const rows = cols === 1 ? rowsFit : Math.min(MAX_DEFAULT_ROWS, rowsFit);
      const fit = Math.min(
        quickCards.length,
        Math.max(MOBILE_MIN_VISIBLE, rows * cols),
      );
      setDefaultVisible((prev) => (prev === fit ? prev : fit));
    };

    compute();

    let raf = 0;
    const schedule = () => {
      if (raf) return;
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        compute();
      });
    };

    const ro = new ResizeObserver(schedule);
    if (welcomeRef.current) ro.observe(welcomeRef.current);
    window.addEventListener("resize", schedule);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", schedule);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, [isMobile, quickCards.length]);

  useEffect(() => {
    setExpanded(false);
  }, [isMobile]);

  const visibleCount = expanded ? quickCards.length : defaultVisible;
  const showToggle = quickCards.length > defaultVisible;
  const cards = quickCards.slice(0, visibleCount);

  return {
    welcomeRef,
    headingRef,
    sectionTitleRef,
    probeRef,
    expanded,
    setExpanded,
    cards,
    showToggle,
    isMobile,
    autoHideMascot,
  };
}
