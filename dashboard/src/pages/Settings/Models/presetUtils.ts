import type { ProviderPreset, ProviderRow } from "./useProviders";

export interface PresetGroup {
  groupKey: string;
  groupName: string;
  presets: ProviderPreset[];
}

/** Preset brand card order (swap Tencent Cloud / Aliyun vs pure alphabetical). */
const PRESET_GROUP_ORDER = [
  "tencent",
  "kimi",
  "minimax",
  "opencode",
  "siliconflow",
  "aliyun",
  "volcengine",
  "zhipu",
] as const;

function comparePresetGroups(a: PresetGroup, b: PresetGroup): number {
  const ai = PRESET_GROUP_ORDER.indexOf(
    a.groupKey as (typeof PRESET_GROUP_ORDER)[number],
  );
  const bi = PRESET_GROUP_ORDER.indexOf(
    b.groupKey as (typeof PRESET_GROUP_ORDER)[number],
  );
  const aRank = ai === -1 ? Number.MAX_SAFE_INTEGER : ai;
  const bRank = bi === -1 ? Number.MAX_SAFE_INTEGER : bi;
  if (aRank !== bRank) return aRank - bRank;
  return a.groupName.localeCompare(b.groupName);
}

const VARIANT_LABELS: Record<string, string> = {
  dashscope: "DashScope",
  dashscope_intl: "Singapore",
  dashscope_us: "US",
  open_platform: "Open Platform",
  open_platform_cn: "China",
  open_platform_intl: "International",
  coding_plan: "Coding Plan",
  coding_plan_cn: "Coding (CN)",
  coding_plan_intl: "Coding (Intl)",
  token_plan: "Token Plan",
  token_plan_intl: "Token (Intl)",
  hai: "HAI",
  china: "China",
  international: "International",
  zen_compatible: "Zen · Compatible",
  zen_anthropic: "Zen · Anthropic",
  go_compatible: "Go · Compatible",
  go_anthropic: "Go · Anthropic",
};

export function presetVariantLabel(preset: ProviderPreset): string {
  if (preset.provider_variant && VARIANT_LABELS[preset.provider_variant]) {
    return VARIANT_LABELS[preset.provider_variant];
  }
  return preset.name;
}

export function presetLogoId(preset: ProviderPreset): string {
  return preset.logo_id || preset.id;
}

export function findConfiguredProvider(
  preset: ProviderPreset,
  providers: ProviderRow[],
): ProviderRow | undefined {
  return providers.find((p) => p.name === preset.name || p.name === preset.id);
}

export function groupPresets(presets: ProviderPreset[]): {
  grouped: PresetGroup[];
  ungrouped: ProviderPreset[];
} {
  const groupMap = new Map<string, PresetGroup>();
  const ungrouped: ProviderPreset[] = [];

  for (const preset of presets) {
    if (preset.provider_group) {
      const existing = groupMap.get(preset.provider_group);
      if (existing) {
        existing.presets.push(preset);
      } else {
        groupMap.set(preset.provider_group, {
          groupKey: preset.provider_group,
          groupName: preset.provider_group_name || preset.provider_group,
          presets: [preset],
        });
      }
    } else {
      ungrouped.push(preset);
    }
  }

  const grouped: PresetGroup[] = [];
  for (const group of groupMap.values()) {
    if (group.presets.length >= 2) {
      grouped.push(group);
    } else {
      ungrouped.push(...group.presets);
    }
  }

  grouped.sort(comparePresetGroups);
  ungrouped.sort((a, b) => a.name.localeCompare(b.name));
  return { grouped, ungrouped };
}

export function isPresetProvider(
  provider: ProviderRow,
  presets: ProviderPreset[],
): boolean {
  return presets.some(
    (preset) => provider.name === preset.name || provider.name === preset.id,
  );
}

const LOCAL_PRESET_IDS = new Set(["ollama"]);

export function isLocalPreset(preset: ProviderPreset): boolean {
  return LOCAL_PRESET_IDS.has(preset.id);
}
