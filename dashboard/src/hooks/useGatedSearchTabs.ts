import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useCurrentUser } from "./useCurrentUser";
import { userCanKey } from "../utils/permissions";

/**
 * Search-param tabs filtered by module permission.
 * Unknown / missing ``?tab=`` redirects to the first allowed tab.
 * An explicit disallowed tab stays and ``forbidden`` is true.
 */
export function useGatedSearchTabs<T extends string, TTab extends { key: T }>({
  tabs,
  tabPermissions,
  parseTab,
  querylessKey,
}: {
  tabs: readonly TTab[];
  tabPermissions: Record<T, string | readonly string[]>;
  parseTab: (raw: string | null) => T;
  querylessKey: T;
}) {
  const user = useCurrentUser();
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("tab");
  const requested = parseTab(raw);
  const explicitKnown = raw !== null && tabs.some((tab) => tab.key === raw);

  const allowedTabs = useMemo(
    () =>
      user
        ? tabs.filter((tab) => userCanKey(user, tabPermissions[tab.key]))
        : [],
    [tabs, user, tabPermissions],
  );

  const requestedAllowed = allowedTabs.some((tab) => tab.key === requested);
  const forbidden = Boolean(user && explicitKnown && !requestedAllowed);

  useEffect(() => {
    if (!user || forbidden || requestedAllowed) return;
    const first = allowedTabs[0];
    if (!first) return;
    const next = new URLSearchParams(searchParams);
    if (first.key === querylessKey) {
      if (!next.has("tab")) return;
      next.delete("tab");
    } else {
      next.set("tab", first.key);
    }
    setSearchParams(next, { replace: true });
  }, [
    user,
    forbidden,
    requestedAllowed,
    allowedTabs,
    querylessKey,
    searchParams,
    setSearchParams,
  ]);

  const selectTab = (key: T) => {
    const next = new URLSearchParams(searchParams);
    if (key === querylessKey) {
      next.delete("tab");
    } else {
      next.set("tab", key);
    }
    setSearchParams(next, { replace: true });
  };

  const activeTab: T = requestedAllowed
    ? requested
    : allowedTabs[0]?.key ?? requested;

  return {
    user,
    allowedTabs,
    activeTab,
    forbidden: forbidden || Boolean(user && allowedTabs.length === 0),
    selectTab,
  };
}
