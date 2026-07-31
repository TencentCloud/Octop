import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  preferencesApi,
  type RemoteBrowserBookmark,
} from "../api/modules/preferences";
import { normalizeUrl } from "../utils/normalizeUrl";
import { showApiError } from "../utils/showApiToast";

import { message } from "@/utils/antdMessage";

const MAX_BOOKMARKS = 12;

function bookmarkTitle(url: string, title: string): string {
  const trimmed = title.trim();
  if (trimmed && trimmed !== "about:blank") return trimmed;
  try {
    return new URL(url).hostname || url;
  } catch {
    return url;
  }
}

export function useRemoteBrowserBookmarks() {
  const { t } = useTranslation();
  const [bookmarks, setBookmarks] = useState<RemoteBrowserBookmark[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void preferencesApi
      .get()
      .then((prefs) => {
        if (!cancelled) {
          setBookmarks(prefs.remote_browser_bookmarks ?? []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          showApiError(err, t("remoteBrowser.bookmarkLoadFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const persist = useCallback(
    async (next: RemoteBrowserBookmark[]) => {
      const prev = bookmarks;
      setBookmarks(next);
      try {
        const res = await preferencesApi.patch({
          remote_browser_bookmarks: next,
        });
        setBookmarks(res.remote_browser_bookmarks ?? next);
      } catch (err) {
        setBookmarks(prev);
        showApiError(err, t("remoteBrowser.bookmarkSaveFailed"));
      }
    },
    [bookmarks, t],
  );

  const isBookmarked = useCallback(
    (url: string) => {
      const normalized = normalizeUrl(url);
      if (!normalized) return false;
      return bookmarks.some((b) => normalizeUrl(b.url) === normalized);
    },
    [bookmarks],
  );

  const toggle = useCallback(
    (url: string, title: string) => {
      const normalized = normalizeUrl(url);
      if (!normalized) return;
      if (isBookmarked(normalized)) {
        const next = bookmarks.filter(
          (b) => normalizeUrl(b.url) !== normalized,
        );
        void persist(next);
        message.success(t("remoteBrowser.bookmarkRemoved"));
        return;
      }
      if (bookmarks.length >= MAX_BOOKMARKS) {
        message.warning(t("remoteBrowser.bookmarkLimit"));
        return;
      }
      const next = [
        ...bookmarks,
        { url: normalized, title: bookmarkTitle(normalized, title) },
      ];
      void persist(next);
      message.success(t("remoteBrowser.bookmarkSaved"));
    },
    [bookmarks, isBookmarked, persist, t],
  );

  const remove = useCallback(
    (url: string) => {
      const normalized = normalizeUrl(url);
      if (!normalized) return;
      const next = bookmarks.filter((b) => normalizeUrl(b.url) !== normalized);
      void persist(next);
    },
    [bookmarks, persist],
  );

  return { bookmarks, loading, isBookmarked, toggle, remove };
}
