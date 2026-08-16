import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request }));

import { publishedExpertsApi } from "./publishedExperts";

beforeEach(() => {
  request.mockClear();
});

describe("publishedExpertsApi", () => {
  it("uses publish lifecycle endpoints for an agent-owned template", () => {
    publishedExpertsApi.list();
    publishedExpertsApi.publish("agent-1", {
      name: "Research assistant",
      description: "Finds sources",
      slug: "research-assistant",
    });
    publishedExpertsApi.refresh("expert/1", {
      name: "Updated",
      description: "New description",
      welcome_message: { zh: "欢迎", en: "Welcome" },
    });
    publishedExpertsApi.unpublish("expert/1");

    expect(request).toHaveBeenNthCalledWith(1, "/experts/published");
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/agents/agent-1/publish-expert",
      {
        method: "POST",
        body: JSON.stringify({
          name: "Research assistant",
          description: "Finds sources",
          slug: "research-assistant",
        }),
      },
    );
    expect(request).toHaveBeenNthCalledWith(
      3,
      "/experts/published/expert%2F1/refresh",
      {
        method: "POST",
      },
    );
    expect(request).toHaveBeenNthCalledWith(
      4,
      "/experts/published/expert%2F1",
      {
        method: "DELETE",
      },
    );
  });

  it("installs a published template with its chosen agent details", () => {
    publishedExpertsApi.install("expert-1", {
      name: "My research assistant",
      description: "Personal copy",
    });

    expect(request).toHaveBeenCalledWith(
      "/experts/published/expert-1/install",
      {
        method: "POST",
        body: JSON.stringify({
          name: "My research assistant",
          description: "Personal copy",
        }),
      },
    );
  });
});
