import { useState } from "react";
import { useIsMobile } from "./useIsMobile";

export type CardTableViewMode = "card" | "table";

/**
 * Shared card/table view toggle.
 * The selected mode is honoured on all viewports (including mobile);
 * tables rely on existing horizontal-scroll CSS in layout.css.
 */
export function useCardTableView(defaultMode: CardTableViewMode = "table") {
  const isMobile = useIsMobile();
  const [viewMode, setViewMode] = useState<CardTableViewMode>(defaultMode);
  const showCardView = viewMode === "card";
  return { isMobile, viewMode, setViewMode, showCardView };
}
