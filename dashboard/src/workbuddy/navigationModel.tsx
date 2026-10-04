import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { useServerCapabilities } from "../hooks/useServerCapabilities";
import { preferencesApi } from "../api/modules/preferences";
import { buildNavSections, type NavSection } from "../layouts/sidebarNav";
import {
  sectionsFromLayout,
  type SidebarNavLayout,
} from "../layouts/sidebarNavLayout";

export const MARKET_KEYS = new Set([
  "experts",
  "personalization",
  "channels",
  "connectors",
  "skill-packages",
]);
export const CONTROL_KEYS = new Set([
  "workbench",
  "remote-desktop",
  "acp",
  "bridge",
]);
export const MANAGEMENT_KEYS = new Set([
  "models",
  "admin-users",
  "admin-storage",
  "admin-plugins",
  "admin-security",
  "admin-advanced",
]);
export function workBuddyLabelKey(key: string, fallback: string): string {
  return key === "workbench" ? "workbuddy.controlConsole" : fallback;
}
export function filterNavigation(
  sections: NavSection[],
  keys: ReadonlySet<string>,
): NavSection[] {
  return sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => keys.has(item.key)),
    }))
    .filter((section) => section.items.length > 0);
}
const NavigationContext = createContext<{
  catalog: NavSection[];
  sections: NavSection[];
  savedLayout: SidebarNavLayout | null;
  setSavedLayout: (layout: SidebarNavLayout | null) => void;
}>({ catalog: [], sections: [], savedLayout: null, setSavedLayout: () => {} });

export function WorkBuddyNavigationProvider({
  children,
}: {
  children: ReactNode;
}) {
  const user = useCurrentUser();
  const { mobileEnabled } = useServerCapabilities();
  const catalog = useMemo(
    () => buildNavSections(user, { mobileEnabled }),
    [user, mobileEnabled],
  );
  const username = user?.username;
  const [savedLayout, setSavedLayout] = useState<SidebarNavLayout | null>(null);
  useEffect(() => {
    let cancelled = false;
    setSavedLayout(null);
    if (username)
      void preferencesApi
        .get()
        .then((prefs) => {
          if (!cancelled) setSavedLayout(prefs.sidebar_nav ?? null);
        })
        .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [username]);
  const sections = useMemo(
    () => sectionsFromLayout(catalog, savedLayout),
    [catalog, savedLayout],
  );
  return (
    <NavigationContext.Provider
      value={{ catalog, sections, savedLayout, setSavedLayout }}
    >
      {children}
    </NavigationContext.Provider>
  );
}
export function useWorkBuddyNavigation() {
  return useContext(NavigationContext);
}
