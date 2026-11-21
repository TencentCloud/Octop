import { describe, expect, it } from "vitest";
import {
  initialMagpieModels,
  isMagpieDefaultBaseUrl,
  isMagpieProvider,
  magpieModelFromCatalog,
  magpieRefreshBody,
  magpieRefreshConnectionChanged,
  magpieRefreshLeavesDirty,
  planMagpieSync,
} from "./magpie";
import type { ProviderModel } from "./useProviders";

describe("magpie sync", () => {
  it("matches only the default loopback address", () => {
    expect(isMagpieDefaultBaseUrl("http://127.0.0.1:3425/v1")).toBe(true);
    expect(isMagpieDefaultBaseUrl("http://127.0.0.1:3425/v1/")).toBe(true);
    expect(isMagpieDefaultBaseUrl("https://127.0.0.1:3425/v1")).toBe(false);
    expect(isMagpieDefaultBaseUrl("http://localhost:3425/v1")).toBe(false);
    expect(
      isMagpieProvider({
        name: "Desk",
        base_url: "https://gateway.example/v1",
        integration: "magpie",
      }),
    ).toBe(true);
    expect(isMagpieProvider({ name: "my-magpie-gateway" })).toBe(false);
  });

  it("refuses an empty first catalog and keeps overrides on refresh", () => {
    expect(initialMagpieModels([])).toBeNull();
    const created = initialMagpieModels([
      { id: "vendor/org/model", name: "Shown" },
      { id: "vendor/org/model", name: "dup" },
    ]);
    expect(created?.map((model) => model.id)).toEqual(["vendor/org/model"]);
    expect(created?.[0].enabled).toBe(true);

    const existing: ProviderModel[] = [
      {
        id: "keep/me",
        name: "Old",
        enabled: false,
        input: ["text", "image"],
        visibility: "groups",
        group_ids: ["design"],
      },
      { id: "gone", name: "Gone", enabled: true },
    ];
    const plan = planMagpieSync(existing, [
      { id: "keep/me", name: "New" },
      { id: "added", name: "Added" },
    ]);
    expect(plan.added).toEqual(["added"]);
    expect(plan.removed).toEqual(["gone"]);
    expect(plan.models[0]).toMatchObject({
      name: "Old",
      enabled: false,
      input: ["text", "image"],
      group_ids: ["design"],
    });
    expect(plan.models[1].enabled).toBe(false);

    const wipe = planMagpieSync(existing, []);
    expect(wipe.models).toEqual([]);
    expect(wipe.removed).toEqual(["keep/me", "gone"]);
  });

  it("keeps fetched capabilities for a manual preset add", () => {
    const model = magpieModelFromCatalog({
      id: "deepseek/deepseek-v4-flash",
      name: "DeepSeek V4 Flash",
      input: ["text", "image"],
      context_window: 1_000_000,
      max_tokens: 393_000,
      reasoning: true,
      reasoning_config: {
        supported: true,
        toggle: true,
        default_mode: "auto",
        efforts: ["low", "high"],
        effort_type: "enum",
        adapter: "thinking",
      },
    });
    expect(model).toMatchObject({
      id: "deepseek/deepseek-v4-flash",
      name: "DeepSeek V4 Flash",
      enabled: false,
      input: ["text", "image"],
      context_window: 1_000_000,
      max_tokens: 393_000,
      reasoning: true,
      reasoning_config: { adapter: "thinking", default_mode: "auto" },
    });
  });

  it("saves a changed address and key with the catalog and keeps other edits dirty", () => {
    const models: ProviderModel[] = [
      { id: "deepseek/deepseek-v4-flash", name: "Flash", enabled: true },
    ];
    const unchanged = magpieRefreshBody({
      models,
      savedBaseUrl: "http://127.0.0.1:3425/v1",
      draftBaseUrl: "http://127.0.0.1:3425/v1",
      draftApiKey: "",
    });
    expect(unchanged).toEqual({ models });
    expect(magpieRefreshConnectionChanged(unchanged)).toBe(false);

    const changed = magpieRefreshBody({
      models,
      savedBaseUrl: "http://127.0.0.1:3425/v1",
      draftBaseUrl: "https://gateway.example/v1",
      draftApiKey: "sk-real",
    });
    expect(changed.base_url).toBe("https://gateway.example/v1");
    expect(changed.api_key).toBe("sk-real");
    expect(
      magpieRefreshLeavesDirty(
        changed,
        {
          base_url: "http://127.0.0.1:3425/v1",
          note: "",
          model: "",
          kind: "openai",
          stream_usage: true,
        },
        {
          base_url: "https://gateway.example/v1",
          api_key: "sk-real",
          note: "remote desk",
          model: "",
          kind: "openai",
          stream_usage: true,
        },
      ),
    ).toBe(true);
    expect(
      magpieRefreshLeavesDirty(
        changed,
        {
          base_url: "http://127.0.0.1:3425/v1",
          note: "",
          model: "",
          kind: "openai",
          stream_usage: true,
        },
        {
          base_url: "https://gateway.example/v1",
          api_key: "sk-real",
          note: "",
          model: "",
          kind: "openai",
          stream_usage: true,
        },
      ),
    ).toBe(false);
  });
});
