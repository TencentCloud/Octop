import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request }));

import { customExpertTemplatesApi } from "./customExpertTemplates";

beforeEach(() => {
  request.mockClear();
});

describe("customExpertTemplatesApi", () => {
  it("uses the admin preview, publish, and delete endpoints", () => {
    const body = {
      template_id: "team-writer",
      label_zh: "团队写手",
      label_en: "Team Writer",
      description_zh: "团队内容模板",
      description_en: "Organization writing template",
    };

    customExpertTemplatesApi.preview("agent-1");
    customExpertTemplatesApi.publish("agent-1", body);
    customExpertTemplatesApi.delete("team-writer");

    expect(request).toHaveBeenNthCalledWith(
      1,
      "/admin/agents/agent-1/expert-template/preview",
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/admin/agents/agent-1/expert-template",
      { method: "POST", body: JSON.stringify(body) },
    );
    expect(request).toHaveBeenNthCalledWith(
      3,
      "/admin/expert-templates/team-writer",
      { method: "DELETE" },
    );
  });
});
