import { useLayoutEffect, useRef, useState } from "react";
import { requestBlob } from "../api/request";
import {
  asImageBlob,
  isDataUrl,
  needsAuthBlobFetch,
} from "../utils/toolMediaBlocks";

export type AuthImageLoadState = "loading" | "ready" | "error";

type HeldAuthImage = { url: string; filename?: string };

type AuthImageCacheEntry = {
  objectUrl?: string;
  refs: number;
  inflight?: Promise<string>;
};

const authImageCache = new Map<string, AuthImageCacheEntry>();

function apiPathFromUrl(url: string): string {
  if (url.startsWith("http")) {
    const parsed = new URL(url);
    return parsed.pathname.replace(/^\/api/, "") + parsed.search;
  }
  return url.replace(/^\/api/, "");
}

export async function fetchAuthImageBlob(
  url: string,
  filename?: string,
): Promise<Blob> {
  if (isDataUrl(url)) {
    const res = await fetch(url);
    return asImageBlob(await res.blob(), filename);
  }
  const blob = await requestBlob(apiPathFromUrl(url), { cache: "no-store" });
  return asImageBlob(blob, filename);
}

function cacheKey(url: string, filename?: string): string {
  return filename ? `${url}\0${filename}` : url;
}

export function acquireAuthImageSrc(
  url: string,
  filename?: string,
): Promise<string> {
  const key = cacheKey(url, filename);
  let entry = authImageCache.get(key);
  if (!entry) {
    entry = { refs: 0 };
    authImageCache.set(key, entry);
  }
  entry.refs += 1;
  if (entry.objectUrl) {
    return Promise.resolve(entry.objectUrl);
  }
  if (!entry.inflight) {
    const pending = entry;
    pending.inflight = fetchAuthImageBlob(url, filename)
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        pending.objectUrl = objectUrl;
        pending.inflight = undefined;
        if (pending.refs <= 0) {
          URL.revokeObjectURL(objectUrl);
          authImageCache.delete(key);
        }
        return objectUrl;
      })
      .catch((err: unknown) => {
        pending.inflight = undefined;
        if (pending.refs <= 0) {
          authImageCache.delete(key);
        }
        throw err;
      });
  }
  if (!entry.inflight) {
    throw new Error("auth image cache missing inflight");
  }
  return entry.inflight;
}

export function releaseAuthImageSrc(url: string, filename?: string): void {
  const key = cacheKey(url, filename);
  const entry = authImageCache.get(key);
  if (!entry) return;
  entry.refs -= 1;
  if (entry.refs > 0 || entry.inflight) return;
  if (entry.objectUrl) {
    URL.revokeObjectURL(entry.objectUrl);
  }
  authImageCache.delete(key);
}

function releaseHeld(held: HeldAuthImage | undefined): void {
  if (!held) return;
  releaseAuthImageSrc(held.url, held.filename);
}

/** Load JWT-protected or data-URL images into a blob object URL. */
export function useAuthImageSrc(
  url: string,
  filename?: string,
): {
  src: string;
  loadState: AuthImageLoadState;
  setSrc: React.Dispatch<React.SetStateAction<string>>;
} {
  const needsFetch = needsAuthBlobFetch(url) || isDataUrl(url);
  const [src, setSrc] = useState(() => (needsFetch ? "" : url));
  const [loadState, setLoadState] = useState<AuthImageLoadState>(() =>
    needsFetch ? "loading" : "ready",
  );
  const heldRef = useRef<HeldAuthImage | undefined>(undefined);

  useLayoutEffect(() => {
    if (!needsAuthBlobFetch(url) && !isDataUrl(url)) {
      releaseHeld(heldRef.current);
      heldRef.current = undefined;
      setSrc(url);
      setLoadState("ready");
      return;
    }

    let cancelled = false;
    setLoadState("loading");

    const load = async () => {
      try {
        const objectUrl = await acquireAuthImageSrc(url, filename);
        if (cancelled) {
          releaseAuthImageSrc(url, filename);
          return;
        }
        if (
          heldRef.current &&
          (heldRef.current.url !== url || heldRef.current.filename !== filename)
        ) {
          releaseHeld(heldRef.current);
        }
        heldRef.current = { url, filename };
        setSrc(objectUrl);
        setLoadState("ready");
      } catch {
        releaseAuthImageSrc(url, filename);
        if (!cancelled) {
          setSrc("");
          setLoadState("error");
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [url, filename]);

  useLayoutEffect(() => {
    return () => {
      releaseHeld(heldRef.current);
      heldRef.current = undefined;
    };
  }, []);

  return { src, loadState, setSrc };
}
