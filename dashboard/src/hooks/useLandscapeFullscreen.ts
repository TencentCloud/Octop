import { useCallback, useEffect, type RefObject } from "react";

interface UseLandscapeFullscreenOptions {
  isMobile: boolean;
  onError?: () => void;
}

type OrientableScreen = ScreenOrientation & {
  lock?: (orientation: string) => Promise<void>;
  unlock?: () => void;
};

function screenOrientation(): OrientableScreen | undefined {
  return screen.orientation as OrientableScreen | undefined;
}

function tryUnlockOrientation(): void {
  try {
    screenOrientation()?.unlock?.();
  } catch {
    /* ignore */
  }
}

/** Toggle fullscreen on a container; on mobile also tries landscape lock. */
export function useLandscapeFullscreen(
  containerRef: RefObject<HTMLElement | null>,
  { isMobile, onError }: UseLandscapeFullscreenOptions,
) {
  const toggle = useCallback(async () => {
    const el = containerRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement) {
        tryUnlockOrientation();
        await document.exitFullscreen();
      } else {
        await el.requestFullscreen();
        if (isMobile) {
          try {
            await screenOrientation()?.lock?.("landscape");
          } catch {
            /* iOS / unsupported */
          }
        }
      }
    } catch {
      onError?.();
    }
  }, [containerRef, isMobile, onError]);

  useEffect(() => {
    const onFullscreenChange = () => {
      if (!document.fullscreenElement) {
        tryUnlockOrientation();
      }
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () =>
      document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  return toggle;
}
