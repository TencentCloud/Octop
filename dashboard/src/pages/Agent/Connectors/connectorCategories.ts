import type { ConnectorCategory } from "../../../api/modules/connectors";

/** Empty value means every category, matching the expert-market "all" pill. */
export const CONNECTOR_CATEGORY_ALL = "";

/** Stable pill order. Categories missing from the catalog are omitted. */
export const CONNECTOR_CATEGORY_ORDER: readonly ConnectorCategory[] = [
  "office",
  "knowledge",
  "travel",
  "productivity",
  "media",
  "professional",
  "self_hosted",
];

export interface ConnectorCategoryOption {
  value: string;
  label: string;
}

export function connectorCategoryOptions(
  present: Iterable<string>,
  labelFor: (category: string) => string,
  allLabel: string,
): ConnectorCategoryOption[] {
  const have = new Set(present);
  const ordered = CONNECTOR_CATEGORY_ORDER.filter((category) =>
    have.has(category),
  );
  const extras = [...have]
    .filter(
      (category) =>
        !CONNECTOR_CATEGORY_ORDER.includes(category as ConnectorCategory),
    )
    .sort((a, b) => a.localeCompare(b));
  const categories = [...ordered, ...extras];
  if (categories.length === 0) return [];
  return [
    { value: CONNECTOR_CATEGORY_ALL, label: allLabel },
    ...categories.map((category) => ({
      value: category,
      label: labelFor(category),
    })),
  ];
}

export function matchesConnectorCategory(
  category: string | undefined,
  active: string,
): boolean {
  if (!active) return true;
  return category === active;
}
