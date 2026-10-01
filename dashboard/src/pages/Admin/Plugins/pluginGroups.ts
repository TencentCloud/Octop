/** Known plugin catalog group slugs (``plugin.yaml`` → ``group``). */
export const PLUGIN_GROUP_ORDER = [
  "lifestyle",
  "news",
  "finance",
  "media",
  "fun",
  "games",
  "tools",
  "ops",
] as const;

export type PluginGroupId = (typeof PLUGIN_GROUP_ORDER)[number];

export function isKnownPluginGroup(
  value: string | null | undefined,
): value is PluginGroupId {
  return !!value && (PLUGIN_GROUP_ORDER as readonly string[]).includes(value);
}
