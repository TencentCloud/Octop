import { useEffect, type RefObject } from "react";
import { measureVisualViewportOverflow } from "./viewport";

/**
 * If `el` extends below the visual viewport, translate it up just enough to
 * stay visible. Used by the chat composer on mobile browser (Android Chrome).
 */
export function useKeepInVisualViewport(
  ref: RefObject<HTMLElement | null>,
  enabled: boolean,
) {
  useEffect(() => {
    if (!enabled) return;
    const vv = window.visualViewport;
    if (!vv) return;

    let raf = 0;

    const clear = () => {
      const node = ref.current;
      if (!node) return;
      node.style.removeProperty("translate");
      node.style.removeProperty("will-change");
    };

    const update = () => {
      cancelAnimationFrame(raf);
      raf = window.requestAnimationFrame(() => {
        const node = ref.current;
        if (!node) return;
        node.style.removeProperty("translate");
        const overflow = measureVisualViewportOverflow(
          node.getBoundingClientRect().bottom,
          vv,
        );
        if (overflow > 0.5) {
          node.style.willChange = "translate";
          node.style.translate = `0 ${-Math.ceil(overflow)}px`;
        }
      });
    };

    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    update();

    return () => {
      cancelAnimationFrame(raf);
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
      clear();
    };
  }, [enabled, ref]);
}

export { measureVisualViewportOverflow } from "./viewport";
