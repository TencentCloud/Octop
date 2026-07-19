/** Remote desktop stream presets (resolution + frame rate). */

export type DesktopResolution = "1280x800" | "1440x900" | "1920x1080";

export const DESKTOP_RESOLUTION_OPTIONS: {
  value: DesktopResolution;
  width: number;
  height: number;
}[] = [
  { value: "1280x800", width: 1280, height: 800 },
  { value: "1440x900", width: 1440, height: 900 },
  { value: "1920x1080", width: 1920, height: 1080 },
];

export const DESKTOP_FPS_PRESETS = [5, 10, 15, 30] as const;
export type DesktopFpsPreset = (typeof DESKTOP_FPS_PRESETS)[number];

export function desktopResolutionLabel(value: DesktopResolution): string {
  return value.replace("x", "×");
}

export function desktopFpsLabel(fps: number): string {
  return `${fps} FPS`;
}

export function isDesktopResolution(value: string): value is DesktopResolution {
  return DESKTOP_RESOLUTION_OPTIONS.some((o) => o.value === value);
}
