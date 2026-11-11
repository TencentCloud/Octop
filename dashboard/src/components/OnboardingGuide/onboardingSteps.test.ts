import { describe, expect, it } from "vitest";

import { buildOnboardingSteps } from "./onboardingSteps";

describe("buildOnboardingSteps", () => {
  it("gives admins every step, with models pointing at the models page", () => {
    const steps = buildOnboardingSteps({ role: "admin", permissions: [] });
    expect(steps.map((s) => s.key)).toEqual([
      "welcome",
      "chat",
      "experts",
      "models",
      "channels",
      "knowledgeBases",
      "skillPackages",
    ]);
    expect(steps.find((s) => s.key === "models")).toMatchObject({
      path: "/admin/models",
      bodyKey: "body",
    });
    expect(steps[0].path).toBeNull();
    expect(steps.slice(1).every((s) => s.path?.startsWith("/"))).toBe(true);
  });

  it("points members without the models page at the chat model picker", () => {
    const steps = buildOnboardingSteps({
      role: "user",
      permissions: ["experts", "channels", "knowledge_bases", "skill_packages"],
    });
    expect(steps.map((s) => s.key)).toEqual([
      "welcome",
      "chat",
      "experts",
      "models",
      "channels",
      "knowledgeBases",
      "skillPackages",
    ]);
    expect(steps.find((s) => s.key === "models")).toMatchObject({
      path: "/chat",
      bodyKey: "bodyMember",
    });
  });

  it("drops steps for pages the user cannot open", () => {
    const steps = buildOnboardingSteps({
      role: "user",
      permissions: ["knowledge_bases"],
    });
    expect(steps.map((s) => s.key)).toEqual([
      "welcome",
      "chat",
      "models",
      "knowledgeBases",
    ]);
  });
});
