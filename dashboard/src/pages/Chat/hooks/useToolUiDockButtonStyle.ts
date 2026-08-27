import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type RefObject,
} from "react";

const DOCK_BTN_SIZE = 28;
const DOCK_BTN_INSET = 8;

function findToolUiCard(root: HTMLElement): HTMLElement | null {
  return (
    root.querySelector<HTMLElement>("[data-octop-plugin-ui]") ??
    root.querySelector<HTMLElement>(".octop-builtin-ui-fallback") ??
    null
  );
}

/**
 * Place the dock button at the top-right of the plugin card without changing
 * the card's layout width (avoid fit-content / inline-grid shrink-to-fit).
 */
export function useToolUiDockButtonStyle(
  enabled: boolean,
  deps: unknown[] = [],
): {
  wrapRef: RefObject<HTMLDivElement>;
  buttonStyle: CSSProperties | undefined;
} {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [buttonStyle, setButtonStyle] = useState<CSSProperties | undefined>();

  const update = useCallback(() => {
    const root = wrapRef.current;
    if (!root || !enabled) {
      setButtonStyle(undefined);
      return;
    }
    const card = findToolUiCard(root);
    if (!card) {
      setButtonStyle({ top: DOCK_BTN_INSET, right: DOCK_BTN_INSET });
      return;
    }
    const rootRect = root.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    setButtonStyle({
      top: Math.max(0, cardRect.top - rootRect.top) + DOCK_BTN_INSET,
      left:
        Math.max(0, cardRect.right - rootRect.left) -
        DOCK_BTN_SIZE -
        DOCK_BTN_INSET,
    });
  }, [enabled]);

  useLayoutEffect(() => {
    update();
    if (!enabled) return;
    const root = wrapRef.current;
    if (!root) return;

    const ro = new ResizeObserver(() => update());
    ro.observe(root);
    const card = findToolUiCard(root);
    if (card) ro.observe(card);

    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller passes render-invalidating deps
  }, [enabled, update, ...deps]);

  return { wrapRef, buttonStyle };
}
