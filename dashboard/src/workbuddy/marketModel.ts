import type { NavSection } from "../layouts/sidebarNav";
export const MARKET_TABS = [
  {
    id: "experts",
    key: "experts",
    path: "/experts",
    label: "workbuddy.market.experts",
  },
  {
    id: "skills",
    key: "personalization",
    path: "/skills",
    label: "workbuddy.market.skills",
  },
  {
    id: "connectors",
    key: "connectors",
    path: "/connectors",
    label: "nav.connectors",
  },
] as const;
export type MarketTab = (typeof MARKET_TABS)[number];
export function marketTabForPath(path: string) {
  return MARKET_TABS.find(
    (tab) => path === tab.path || path.startsWith(tab.path + "/"),
  );
}
export function visibleMarketTabs(sections: NavSection[]) {
  const keys = new Set(
    sections.flatMap((section) => section.items.map((item) => item.key)),
  );
  return sections
    .flatMap((section) => section.items)
    .flatMap((item) => {
      const tab = MARKET_TABS.find((entry) => entry.key === item.key);
      return tab && keys.has(tab.key) ? [tab] : [];
    });
}
