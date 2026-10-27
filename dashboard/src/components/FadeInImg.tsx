import { useCallback, useState } from "react";
import type { ImgHTMLAttributes } from "react";
import styles from "./FadeInImg.module.less";

type FadeInImgProps = ImgHTMLAttributes<HTMLImageElement>;

/** Image that stays transparent until decode finishes, then fades in. */
export function FadeInImg({
  className,
  src,
  onLoad,
  ...rest
}: FadeInImgProps) {
  const [shownSrc, setShownSrc] = useState<string | undefined>(undefined);
  const shown = shownSrc != null && shownSrc === src;

  const reveal = useCallback((node: HTMLImageElement) => {
    if (node.naturalWidth <= 0) return;
    const current = node.getAttribute("src") ?? undefined;
    requestAnimationFrame(() => setShownSrc(current));
  }, []);

  const ref = useCallback(
    (node: HTMLImageElement | null) => {
      if (node?.complete) reveal(node);
    },
    [reveal],
  );

  return (
    <img
      {...rest}
      ref={ref}
      src={src}
      className={
        shown
          ? `${styles.img} ${styles.ready} ${className ?? ""}`
          : `${styles.img} ${className ?? ""}`
      }
      onLoad={(event) => {
        reveal(event.currentTarget);
        onLoad?.(event);
      }}
    />
  );
}
