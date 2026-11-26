import { afterEach, describe, expect, it } from "vitest";
import * as catalogue from "./constants";
import type { ChannelKey } from "./constants";

const entry = {
  kind: "acme",
  label: "Acme",
  icon: "data:image/svg+xml;base64,PHN2Zy8+",
  intro_url: "https://example.com/help",
  description: "Connect Acme conversations",
  plugin_id: "acme-plugin",
  fields: [
    {
      name: "stream",
      type: "switch",
      helpKey: "channels.streamHelp",
      defaultValue: false,
      legacyDefaultValue: true,
    },
    { name: "limit", type: "text", defaultValue: 0 },
    {
      name: "token",
      type: "password",
      required: true,
      helpKey: "Token help",
      defaultValue: "",
    },
  ],
};

afterEach(() => catalogue.replacePluginChannelKinds([]));

describe("plugin presentation metadata", () => {
  it("retains defaults, help, description and the exact supported icon through replacement", () => {
    expect(catalogue.registerPluginChannelKind(entry)).toBe(true);
    expect(catalogue.registerPluginChannelKind(entry)).toBe(false);
    expect(catalogue.CHANNEL_FIELDS["acme" as ChannelKey]).toMatchObject(
      entry.fields,
    );
    expect(catalogue.CHANNEL_DESCRIPTIONS.acme).toBe(entry.description);
    expect(catalogue.CHANNEL_ICONS["acme" as ChannelKey]).toBe(entry.icon);
    catalogue.replacePluginChannelKinds([
      { ...entry, description: "Updated", fields: [] },
    ]);
    expect(catalogue.CHANNEL_DESCRIPTIONS.acme).toBe("Updated");
    expect(catalogue.CHANNEL_FIELDS["acme" as ChannelKey]).toBeUndefined();
    catalogue.replacePluginChannelKinds([]);
    expect(catalogue.CHANNEL_KEYS).not.toContain("acme");
    expect(catalogue.CHANNEL_DESCRIPTIONS.acme).toBeUndefined();
    expect(catalogue.CHANNEL_ICONS["acme" as ChannelKey]).toBeUndefined();
  });

  it("rejects builtin metadata overrides", () => {
    const original = catalogue.CHANNEL_LABELS.telegram;
    expect(
      catalogue.registerPluginChannelKind({ ...entry, kind: "telegram" }),
    ).toBe(false);
    expect(catalogue.CHANNEL_LABELS.telegram).toBe(original);
  });

  it("overlays a runtime legacy entry and restores all its presentation state", () => {
    const key = "legacy_acme" as ChannelKey;
    const fields = [{ name: "old", label: "Old" }];
    catalogue.CHANNEL_KEYS.push(key);
    catalogue.CHANNEL_LABELS[key] = "Legacy";
    catalogue.CHANNEL_LABEL_KEYS[key] = "channels.legacyLabel";
    catalogue.CHANNEL_ICONS[key] = "legacy.svg";
    catalogue.CHANNEL_URLS[key] = "https://example.com/legacy";
    catalogue.CHANNEL_FIELDS[key] = fields;
    catalogue.CHANNEL_DESCRIPTIONS[key] = "Legacy description";
    try {
      expect(catalogue.registerPluginChannelKind({ ...entry, kind: key })).toBe(
        true,
      );
      expect(catalogue.CHANNEL_LABEL_KEYS[key]).toBeUndefined();
      expect(catalogue.CHANNEL_LABELS[key]).toBe("Acme");
      expect(
        catalogue.CHANNEL_KEYS.filter((kind) => kind === key),
      ).toHaveLength(1);
      catalogue.replacePluginChannelKinds([
        { ...entry, kind: key, label: "Updated" },
      ]);
      expect(catalogue.CHANNEL_LABELS[key]).toBe("Updated");
      catalogue.replacePluginChannelKinds([]);
      expect(catalogue.CHANNEL_KEYS).toContain(key);
      expect(catalogue.CHANNEL_LABELS[key]).toBe("Legacy");
      expect(catalogue.CHANNEL_LABEL_KEYS[key]).toBe("channels.legacyLabel");
      expect(catalogue.CHANNEL_ICONS[key]).toBe("legacy.svg");
      expect(catalogue.CHANNEL_URLS[key]).toBe("https://example.com/legacy");
      expect(catalogue.CHANNEL_FIELDS[key]).toBe(fields);
      expect(catalogue.CHANNEL_DESCRIPTIONS[key]).toBe("Legacy description");
      expect(catalogue.isPluginChannelKind(key)).toBe(false);
    } finally {
      catalogue.replacePluginChannelKinds([]);
      catalogue.CHANNEL_KEYS.splice(catalogue.CHANNEL_KEYS.indexOf(key), 1);
      delete (catalogue.CHANNEL_LABELS as Partial<Record<string, string>>)[key];
      delete (catalogue.CHANNEL_LABEL_KEYS as Partial<Record<string, string>>)[
        key
      ];
      delete (catalogue.CHANNEL_ICONS as Partial<Record<string, string>>)[key];
      delete catalogue.CHANNEL_URLS[key];
      delete catalogue.CHANNEL_FIELDS[key];
      delete catalogue.CHANNEL_DESCRIPTIONS[key];
    }
  });
});
