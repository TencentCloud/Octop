import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export interface UsePathTabsOptions<T extends string> {
  /** Base path without trailing slash, e.g. `/workbench`. */
  basePath: string;
  tabs: readonly T[];
  storageKey: string;
  defaultTab: T;
}

export interface UsePathTabsResult<T extends string> {
  /** Tab from URL, or saved/default when on bare/invalid base path. */
  activeTab: T;
  /** Tab resolved from the current pathname; null on bare/invalid path. */
  pathTab: T | null;
  isBare: boolean;
  handleTabChange: (value: string | number) => void;
  isMounted: (tab: T) => boolean;
  isTab: (value: string | null | undefined) => value is T;
}

/**
 * URL-segment tabs with localStorage memory and lazy keep-alive mounts.
 * Shared by Workbench and Personalization.
 */
export function usePathTabs<T extends string>({
  basePath,
  tabs,
  storageKey,
  defaultTab,
}: UsePathTabsOptions<T>): UsePathTabsResult<T> {
  const location = useLocation();
  const navigate = useNavigate();
  const tabSet = useMemo(() => new Set<string>(tabs), [tabs]);

  const isTab = useCallback(
    (value: string | null | undefined): value is T =>
      typeof value === "string" && tabSet.has(value),
    [tabSet],
  );

  const tabFromPath = useCallback(
    (pathname: string): T | null => {
      if (pathname === basePath) return null;
      const prefix = `${basePath}/`;
      if (!pathname.startsWith(prefix)) return null;
      const segment = pathname.slice(prefix.length).split("/")[0];
      return isTab(segment) ? segment : null;
    },
    [basePath, isTab],
  );

  const readSaved = useCallback((): T => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (isTab(saved)) return saved;
    } catch {
      /* ignore */
    }
    return defaultTab;
  }, [storageKey, isTab, defaultTab]);

  const pathTab = tabFromPath(location.pathname);
  const underBase =
    location.pathname === basePath ||
    location.pathname.startsWith(`${basePath}/`);
  const isBare = location.pathname === basePath;
  const hasInvalidSegment = underBase && !isBare && pathTab === null;
  const activeTab: T = pathTab ?? readSaved();

  const [mounted, setMounted] = useState<Partial<Record<T, boolean>>>(
    () => ({ [activeTab]: true }) as Partial<Record<T, boolean>>,
  );

  // Canonicalize bare base path and unknown tab segments onto a real tab URL.
  useEffect(() => {
    if (!underBase) return;
    if (!isBare && !hasInvalidSegment) return;
    navigate(`${basePath}/${readSaved()}${location.search}${location.hash}`, {
      replace: true,
    });
  }, [
    underBase,
    isBare,
    hasInvalidSegment,
    location.search,
    location.hash,
    navigate,
    basePath,
    readSaved,
  ]);

  useEffect(() => {
    if (!pathTab) return;
    try {
      localStorage.setItem(storageKey, pathTab);
    } catch {
      /* ignore */
    }
  }, [pathTab, storageKey]);

  useEffect(() => {
    setMounted((prev) =>
      prev[activeTab] ? prev : { ...prev, [activeTab]: true },
    );
  }, [activeTab]);

  const handleTabChange = useCallback(
    (value: string | number) => {
      const next = String(value);
      if (!isTab(next) || next === activeTab) return;
      navigate(`${basePath}/${next}${location.search}${location.hash}`, {
        replace: false,
      });
    },
    [activeTab, basePath, isTab, location.search, location.hash, navigate],
  );

  const isMounted = useCallback((tab: T) => Boolean(mounted[tab]), [mounted]);

  return {
    activeTab,
    pathTab,
    isBare,
    handleTabChange,
    isMounted,
    isTab,
  };
}
