import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request }));

import { skillPackagesApi } from "./skillPackages";

beforeEach(() => {
  request.mockClear();
});

describe("skillPackagesApi", () => {
  it("uses the agent package mount endpoints", () => {
    skillPackagesApi.listMounted("agent-1");
    skillPackagesApi.replaceMounted("agent-1", ["pkg-1", "pkg-2"]);

    expect(request).toHaveBeenNthCalledWith(
      1,
      "/agents/agent-1/skill-packages",
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/agents/agent-1/skill-packages",
      {
        method: "PUT",
        body: JSON.stringify({ package_ids: ["pkg-1", "pkg-2"] }),
      },
    );
  });

  it("uses the package and nested skill endpoints", () => {
    skillPackagesApi.create({ name: "starter", description: "Starter skills" });
    skillPackagesApi.update("pkg-1", { name: "renamed" });
    skillPackagesApi.fromSkillHub({
      slug: "starter",
      icon_name: "sparkles",
    });
    skillPackagesApi.createSkill("pkg-1", {
      name: "hello",
      content: "---\nname: hello\n---\n",
    });
    skillPackagesApi.updateSkill("pkg-1", "hello", { content: "# Hello" });
    skillPackagesApi.deleteSkill("pkg-1", "hello");

    expect(request).toHaveBeenNthCalledWith(1, "/skill-packages", {
      method: "POST",
      body: JSON.stringify({
        name: "starter",
        description: "Starter skills",
      }),
    });
    expect(request).toHaveBeenNthCalledWith(2, "/skill-packages/pkg-1", {
      method: "PATCH",
      body: JSON.stringify({ name: "renamed" }),
    });
    expect(request).toHaveBeenNthCalledWith(3, "/skill-packages/from-skillhub", {
      method: "POST",
      body: JSON.stringify({
        slug: "starter",
        icon_name: "sparkles",
      }),
    });
    expect(request).toHaveBeenNthCalledWith(4, "/skill-packages/pkg-1/skills", {
      method: "POST",
      body: JSON.stringify({
        name: "hello",
        content: "---\nname: hello\n---\n",
      }),
    });
    expect(request).toHaveBeenNthCalledWith(
      5,
      "/skill-packages/pkg-1/skills/hello",
      {
        method: "PUT",
        body: JSON.stringify({ content: "# Hello" }),
      },
    );
    expect(request).toHaveBeenNthCalledWith(
      6,
      "/skill-packages/pkg-1/skills/hello",
      { method: "DELETE" },
    );
  });
});
