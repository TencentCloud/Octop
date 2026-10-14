import {
  groupExpertsByConnection,
  type ExpertConnectionGroup,
  type RemoteGroupable,
} from "./remoteExpert";
import { isOwnedExpert, type SharedExpertAccess } from "./sharedExpert";

export function labelSelectorGroups<T extends RemoteGroupable>(
  agents: T[],
  kindLabel: string,
  formatRemote: (connectionName: string) => string,
): ExpertConnectionGroup<T>[] {
  return groupExpertsByConnection(agents, kindLabel).map((group) => {
    if (group.key === "local") return { ...group, label: kindLabel };
    const name = group.label.trim() || group.key;
    return { ...group, label: formatRemote(name) };
  });
}

export function showSelectorGroupLabels(
  expertGroups: { key: string }[],
  teamCount: number,
): boolean {
  const onlyLocalExperts =
    expertGroups.length === 1 &&
    expertGroups[0]?.key === "local" &&
    teamCount === 0;
  return !onlyLocalExperts;
}

/** Matches `.group` / chip gap and `.bar` column gap. */
export const SELECTOR_CHIP_GAP = 6;
export const SELECTOR_GROUP_GAP = 14;

export type BarChipSize = {
  id: string;
  width: number;
  groupKey: string;
  groupLabelWidth: number;
};

export function barChipsWidth(
  chips: BarChipSize[],
  chipGap = SELECTOR_CHIP_GAP,
  groupGap = SELECTOR_GROUP_GAP,
): number {
  if (chips.length === 0) return 0;
  let width = 0;
  let lastGroup: string | null = null;
  for (const chip of chips) {
    if (chip.groupKey !== lastGroup) {
      if (lastGroup !== null) width += groupGap;
      if (chip.groupLabelWidth > 0) width += chip.groupLabelWidth + chipGap;
      lastGroup = chip.groupKey;
    } else {
      width += chipGap;
    }
    width += chip.width;
  }
  return width;
}

function pickLeftChips(
  chips: BarChipSize[],
  selectedId: string | undefined,
  count: number,
): BarChipSize[] {
  if (count <= 0) return [];
  const selected = selectedId
    ? chips.find((chip) => chip.id === selectedId)
    : undefined;
  if (!selected) return chips.slice(0, count);
  if (count === 1) return [selected];
  const others = chips
    .filter((chip) => chip.id !== selected.id)
    .slice(0, count - 1);
  const chosen = new Set([selected.id, ...others.map((chip) => chip.id)]);
  return chips.filter((chip) => chosen.has(chip.id));
}

/**
 * Hide trailing chips when the bar overflows. Always keeps the current
 * selection on the bar; ``hiddenIds`` go behind 「更多」.
 */
export function splitBarOverflow(
  chips: BarChipSize[],
  selectedId: string | undefined,
  available: number,
  moreWidth: number,
): { hiddenIds: string[] } {
  if (chips.length === 0 || available <= 0) return { hiddenIds: [] };
  if (barChipsWidth(chips) <= available) return { hiddenIds: [] };

  const budget = Math.max(0, available - moreWidth - SELECTOR_CHIP_GAP);
  const minCount =
    selectedId && chips.some((chip) => chip.id === selectedId) ? 1 : 0;
  let chosen = pickLeftChips(chips, selectedId, minCount);
  for (let count = chips.length; count >= minCount; count -= 1) {
    const subset = pickLeftChips(chips, selectedId, count);
    if (barChipsWidth(subset) <= budget) {
      chosen = subset;
      break;
    }
  }
  const visible = new Set(chosen.map((chip) => chip.id));
  return {
    hiddenIds: chips
      .filter((chip) => !visible.has(chip.id))
      .map((chip) => chip.id),
  };
}

/**
 * Keep a still-owned selection when this page hides teams.
 * ``undefined`` means do not call ``setActiveAgent``.
 */
export function nextPickerSelection(
  activeAgentId: string | null,
  agents: Array<{ agent_id: string } & SharedExpertAccess>,
  selectable: Array<{ agent_id: string }>,
): string | null | undefined {
  if (activeAgentId) {
    const current = agents.find((agent) => agent.agent_id === activeAgentId);
    if (current && isOwnedExpert(current)) return undefined;
  }
  return selectable[0]?.agent_id ?? null;
}
