import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useIsMobile } from "../../../hooks/useIsMobile";
import type { WelcomeQuickCard } from "../components/WelcomeScreen";

const MAX_DEFAULT_ROWS = 2;
const MOBILE_MIN_VISIBLE = 2;
const MASCOT_ASPECT = 711 / 812;
// Estimated heading height WITHOUT the mascot (avoids a feedback loop where
// hiding the mascot shrinks the heading, which would re-trigger the check).
const HEADING_HEIGHT_NO_MASCOT = 72;
// Hysteresis gap so the mascot does not flicker at the height threshold.
const MASCOT_HIDE_HYSTERESIS = 24;

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
  const [autoHideMascot, setAutoHideMascot] = useState(false);

  useEffect(() => {
    setExpanded(false);
    setDefaultVisible(quickCards.length);
  }, [quickCards]);

  useLayoutEffect(() => {
    const compute = () => {
      const w = window.innerWidth;
      const cols = w < 480 ? 1 : w < 768 ? 2 : w < 1200 ? 2 : 3;
      const maxByRows = MAX_DEFAULT_ROWS * cols;

      const container = welcomeRef.current;
      const probe = probeRef.current;

      // Hide the mascot when the available height cannot fit the mascot
      // plus the heading plus at least two rows of quick-start cards.
      // Uses a fixed heading estimate (not the live heading height) and a
      // hysteresis gap so the toggle does not oscillate near the threshold.
      if (container && probe) {
        const containerRect = container.getBoundingClientRect();
        const sectionTitleHeight =
          sectionTitleRef.current?.getBoundingClientRect().height ?? 0;
        const cardHeight = probe.getBoundingClientRect().height;
        const rowGap = 8;
        const reserved = 48;
        const neededForMascot =
          estimateMascotHeight() +
          HEADING_HEIGHT_NO_MASCOT +
          sectionTitleHeight +
          rowGap +
          2 * (cardHeight + rowGap) +
          reserved;
        if (cardHeight > 0) {
          let next = autoHideMascot;
          if (!autoHideMascot && containerRect.height < neededForMascot) {
            next = true;
          } else if (
            autoHideMascot &&
            containerRect.height > neededForMascot + MASCOT_HIDE_HYSTERESIS
          ) {
            next = false;
          }
          setAutoHideMascot((prev) => (prev === next ? prev : next));
        }
      }

      if (!isMobile) {
        setDefaultVisible(Math.min(quickCards.length, maxByRows));
        return;
      }

      if (!container || !probe || quickCards.length === 0) {
        setDefaultVisible(
          Math.max(MOBILE_MIN_VISIBLE, Math.min(quickCards.length, maxByRows)),
        );
        return;
      }

      const containerRect = container.getBoundingClientRect();
      // Use a fixed heading estimate (with mascot height only when shown) so
      // the card count does not oscillate when the mascot toggles.
      const sectionTitleHeight =
        sectionTitleRef.current?.getBoundingClientRect().height ?? 0;
      const headingHeight =
        HEADING_HEIGHT_NO_MASCOT +
        (autoHideMascot ? 0 : estimateMascotHeight());
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
      setDefaultVisible(fit);
    };

    compute();

    const ro = new ResizeObserver(() => compute());
    if (welcomeRef.current) ro.observe(welcomeRef.current);
    window.addEventListener("resize", compute);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", compute);
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
