import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { ClientSettings } from "../../shared/ipc-contract";

/**
 * Shell-owned client settings, persisted separately from ``config.json``. The
 * renderer may read/write these through the bridge but can never point the
 * update check at another host or authorize an install (§5.3 / §6.2).
 */

const DEFAULTS: ClientSettings = {
  launchAtLogin: false,
  closeBehavior: "tray",
  themeBackground: "system",
  stableOnly: true,
};

const SETTING_KEYS = new Set(Object.keys(DEFAULTS));

export class ClientSettingsStore {
  constructor(private readonly filePath: string) {}

  load(): ClientSettings {
    if (!existsSync(this.filePath)) return { ...DEFAULTS };
    try {
      const raw = JSON.parse(readFileSync(this.filePath, "utf8")) as Record<string, unknown>;
      const out = { ...DEFAULTS };
      for (const key of SETTING_KEYS) {
        const value = raw[key];
        if (value === undefined) continue;
        // Basic shape validation: only accept known scalar values.
        if (key === "stableOnly" || key === "launchAtLogin") {
          if (typeof value === "boolean") (out as Record<string, unknown>)[key] = value;
        } else if (typeof value === "string") {
          (out as Record<string, unknown>)[key] = value;
        }
      }
      return out;
    } catch {
      return { ...DEFAULTS };
    }
  }

  save(patch: Partial<ClientSettings>): ClientSettings {
    const next = { ...this.load(), ...patch };
    const sanitized: Record<string, unknown> = {};
    for (const key of SETTING_KEYS) {
      const value = (next as Record<string, unknown>)[key];
      if (key === "stableOnly" || key === "launchAtLogin") {
        sanitized[key] = value === true;
      } else if (key === "closeBehavior") {
        sanitized[key] = value === "quit" ? "quit" : "tray";
      } else if (key === "themeBackground") {
        sanitized[key] = ["system", "light", "dark"].includes(String(value))
          ? value
          : "system";
      }
    }
    mkdirSync(dirname(this.filePath), { recursive: true });
    writeFileSync(this.filePath, JSON.stringify(sanitized, null, 2), "utf8");
    return sanitized as unknown as ClientSettings;
  }
}

export function defaultClientSettingsPath(userDataDir: string): string {
  return join(userDataDir, "desktop-settings.json");
}
