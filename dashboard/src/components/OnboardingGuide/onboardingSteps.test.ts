import { describe, expect, it } from "vitest";

import { buildOnboardingSteps } from "./onboardingSteps";

const keys = (steps: ReturnType<typeof buildOnboardingSteps>) =>
  steps.map((s) => s.key);

describe("buildOnboardingSteps", () => {
  it("tours admins through every page, models included", () => {
    const steps = buildOnboardingSteps({ role: "admin", permissions: [] });
    expect(keys(steps)).toEqual([
      "chat",
      "experts",
      "models",
      "channels",
      "knowledgeBases",
      "skillPackages",
    ]);
    expect(steps.find((s) => s.key === "models")).toEqual({
      key: "models",
      path: "/admin/models",
      navKey: "models",
      variant: "default",
    });
    // Every step spotlights a real sidebar entry on the page it opens.
    expect(steps.map((s) => s.navKey)).toEqual([
      "chat",
      "experts",
      "models",
      "channels",
      "knowledge-bases",
      "skill-packages",
    ]);
  });

  it("points members without the models page at the chat model picker", () => {
    const steps = buildOnboardingSteps({
      role: "user",
      permissions: ["experts", "channels", "knowledge_bases", "skill_packages"],
    });
    expect(keys(steps)).toEqual([
      "chat",
      "experts",
      "models",
      "channels",
      "knowledgeBases",
      "skillPackages",
    ]);
    expect(steps.find((s) => s.key === "models")).toEqual({
      key: "models",
      path: "/chat",
      navKey: "chat",
      variant: "member",
    });
  });

  it("drops steps for pages the user cannot open", () => {
    const steps = buildOnboardingSteps({
      role: "user",
      permissions: ["knowledge_bases"],
    });
    expect(keys(steps)).toEqual(["chat", "models", "knowledgeBases"]);
  });
});
