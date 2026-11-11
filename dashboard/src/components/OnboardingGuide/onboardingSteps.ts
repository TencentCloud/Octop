import { navAllowed, type PermissionHolder } from "../../utils/permissions";

export type OnboardingStepKey =
  | "welcome"
  | "chat"
  | "experts"
  | "models"
  | "channels"
  | "knowledgeBases"
  | "skillPackages";

export interface OnboardingStep {
  key: OnboardingStepKey;
  /** Page the step's "go" button opens. ``null`` for the intro step. */
  path: string | null;
  /** Locale key suffix under ``onboarding.steps.<key>`` for the body text. */
  bodyKey: "body" | "bodyMember";
}

/**
 * Steps for the welcome guide, filtered to the pages this user can open.
 *
 * Model providers are admin-managed; members without the models page still get
 * the step, pointed at the chat input's model switcher instead.
 */
export function buildOnboardingSteps(
  user: PermissionHolder | null | undefined,
): OnboardingStep[] {
  const steps: OnboardingStep[] = [
    { key: "welcome", path: null, bodyKey: "body" },
    { key: "chat", path: "/chat", bodyKey: "body" },
  ];
  if (navAllowed(user, "experts")) {
    steps.push({ key: "experts", path: "/experts", bodyKey: "body" });
  }
  steps.push(
    navAllowed(user, "models")
      ? { key: "models", path: "/admin/models", bodyKey: "body" }
      : { key: "models", path: "/chat", bodyKey: "bodyMember" },
  );
  if (navAllowed(user, "channels")) {
    steps.push({
      key: "channels",
      path: "/personalization/channels",
      bodyKey: "body",
    });
  }
  if (navAllowed(user, "knowledge-bases")) {
    steps.push({
      key: "knowledgeBases",
      path: "/knowledge-bases",
      bodyKey: "body",
    });
  }
  if (navAllowed(user, "skill-packages")) {
    steps.push({
      key: "skillPackages",
      path: "/skill-packages",
      bodyKey: "body",
    });
  }
  return steps;
}
