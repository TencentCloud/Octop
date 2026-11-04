import type { LucideIcon } from "lucide-react";

/** One tile in the sample-icon grid under the upload controls. */
export interface AvatarPreset {
  id: string;
  /** i18n key; preferred over ``label`` when present. */
  labelKey?: string;
  /** Plain label when no i18n key is available. */
  label?: string;
  bg?: string;
  fg?: string;
  Icon?: LucideIcon;
  /** Image URL (bundled PNG/SVG or static public path). */
  src?: string;
  /**
   * How plain (Lucide-only) tiles render.
   * - ``tinted``: coloured background (user presets)
   * - ``plain``: transparent background, larger glyph (role / lucide grids)
   * - ``portrait``: full-bleed image (inferred when ``src`` is set)
   */
  tone?: "tinted" | "plain" | "portrait";
}

export type AvatarPresetCatalog = readonly AvatarPreset[];
