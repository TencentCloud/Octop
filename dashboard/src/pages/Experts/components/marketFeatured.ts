/** Scene pill for the templates that used to ship as built-in experts. */
export const MARKET_SCENE_FEATURED = "__featured__";

export function visibleMarketExperts<
  T extends { scene?: string; featured?: boolean },
>(items: readonly T[], activeScene: string, searching: boolean): T[] {
  if (searching || !activeScene) return [...items];
  if (activeScene === MARKET_SCENE_FEATURED) {
    return items.filter((item) => item.featured === true);
  }
  const scene = activeScene.toLowerCase();
  return items.filter((item) => (item.scene || "").toLowerCase() === scene);
}
