import { describe, expect, it } from "vitest";

import {
  buildProviderDraft,
  trimmedFormString,
  type MediaProviderDraft,
} from "./index";

function provider(
  overrides: Partial<MediaProviderDraft> = {},
): MediaProviderDraft {
  return {
    id: "volcengine-default",
    provider: "volcengine",
    display_name: "Volcengine",
    enabled: true,
    base_url: "https://ark.example.test/api/v3",
    image_enabled: true,
    video_enabled: true,
    image_model: "doubao-seedream-3-0-t2i",
    video_model: "doubao-seedance-1-0-pro",
    api_key_set: false,
    configured: false,
    api_key: "",
    ...overrides,
  };
}

describe("trimmedFormString", () => {
  it("trims a string the form supplied", () => {
    expect(trimmedFormString("  seedream  ")).toBe("seedream");
  });

  it("returns an empty string for anything the form did not supply", () => {
    expect(trimmedFormString(undefined)).toBe("");
    expect(trimmedFormString(null)).toBe("");
    expect(trimmedFormString(120)).toBe("");
    expect(trimmedFormString({ value: "x" })).toBe("");
  });
});

describe("buildProviderDraft", () => {
  it("keeps the configured model when its input is unmounted", () => {
    // "启用生图工具"/"启用生视频工具" switched off: the model Form.Items
    // unmount, so `validateFields()` does not return them. The preserved store
    // value must still reach the draft — this is the shape that used to throw
    // on `values.image_model.trim()` and leave every modal button inert.
    const validated = {
      provider: "volcengine" as const,
      display_name: "Volcengine",
      base_url: "https://ark.example.test/api/v3",
      api_key: "",
      image_enabled: false,
      video_enabled: false,
    };
    const stored = {
      ...validated,
      image_model: "doubao-seedream-3-0-t2i",
      video_model: "doubao-seedance-1-0-pro",
    };

    const draft = buildProviderDraft(provider(), validated, stored);

    expect(draft.image_model).toBe("doubao-seedream-3-0-t2i");
    expect(draft.video_model).toBe("doubao-seedance-1-0-pro");
    expect(draft.image_enabled).toBe(false);
    expect(draft.video_enabled).toBe(false);
  });

  it("prefers a mounted model input over the preserved value", () => {
    const validated = {
      display_name: "Volcengine",
      base_url: "https://ark.example.test/api/v3",
      api_key: "  sk-live  ",
      image_enabled: true,
      video_enabled: true,
      image_model: "  doubao-seedream-4-0  ",
      video_model: "doubao-seedance-1-0-pro",
    };

    const draft = buildProviderDraft(provider(), validated, {
      ...validated,
      image_model: "stale",
    });

    expect(draft.image_model).toBe("doubao-seedream-4-0");
    expect(draft.api_key).toBe("sk-live");
  });

  it("falls back to an empty model when neither source has one", () => {
    // The exact pre-fix crash: neither `validateFields()` nor the store knows
    // the field, and `.trim()` on `undefined` threw inside a `catch {}` that
    // returned null, so the modal looked unresponsive.
    const validated = {
      display_name: "Volcengine",
      base_url: "https://ark.example.test/api/v3",
      api_key: "",
      image_enabled: false,
      video_enabled: false,
    };

    const draft = buildProviderDraft(
      provider({ image_model: "", video_model: "" }),
      validated,
      validated,
    );

    expect(draft.image_model).toBe("");
    expect(draft.video_model).toBe("");
    expect(draft.display_name).toBe("Volcengine");
  });

  it("keeps the provider identity that is not part of the form", () => {
    const draft = buildProviderDraft(
      provider({ id: "openai-default", provider: "openai", enabled: false }),
      { display_name: "OpenAI" },
      {},
    );

    expect(draft.id).toBe("openai-default");
    expect(draft.provider).toBe("openai");
    expect(draft.enabled).toBe(false);
  });
});
