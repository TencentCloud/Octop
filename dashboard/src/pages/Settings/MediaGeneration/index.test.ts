import { describe, expect, it } from "vitest";

import { normalizeProviderFormValues, type ProviderFormValues } from "./index";

const editingProvider = {
  id: "volcengine-default",
  provider: "volcengine" as const,
  display_name: "Ark",
  enabled: true,
  base_url: "https://ark.example.com",
  image_enabled: true,
  video_enabled: true,
  image_model: "seedream",
  video_model: "seedance",
  api_key_set: true,
  configured: true,
  api_key: "",
};

function values(
  overrides: Partial<ProviderFormValues> = {},
): ProviderFormValues {
  return {
    provider: "volcengine",
    display_name: " Ark ",
    base_url: " https://ark.example.com/ ",
    api_key: "",
    image_enabled: true,
    video_enabled: true,
    image_model: " image-model ",
    video_model: " video-model ",
    ...overrides,
  };
}

describe("normalizeProviderFormValues", () => {
  it("keeps disabled image model fields valid when they are absent", () => {
    const result = normalizeProviderFormValues(
      editingProvider,
      values({ image_enabled: false, image_model: undefined }),
    );

    expect(result.image_model).toBe("");
    expect(result.video_model).toBe("video-model");
  });

  it("keeps disabled video model fields valid when they are absent", () => {
    const result = normalizeProviderFormValues(
      editingProvider,
      values({ video_enabled: false, video_model: undefined }),
    );

    expect(result.image_model).toBe("image-model");
    expect(result.video_model).toBe("");
  });
});
