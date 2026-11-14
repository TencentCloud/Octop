import { navAllowed, type PermissionHolder } from "../../utils/permissions";

export type OnboardingStepKey =
  | "chat"
  | "experts"
  | "models"
  | "channels"
  | "knowledgeBases"
  | "skillPackages";

export interface OnboardingStep {
  key: OnboardingStepKey;
  /** Page the tour opens for this step. */
  path: string;
  /** Sidebar item (``data-nav-key``) the tour spotlights on that page. */
  navKey: string;
  /** Copy variant under ``onboarding.steps.<key>``. */
  variant: "default" | "member";
}

/**
 * Tour steps, filtered to the pages this user can open.
 *
 * Model providers are admin-managed; members without the models page still get
 * the step, pointed at the chat input's model picker instead.
 */
export function buildOnboardingSteps(
  user: PermissionHolder | null | undefined,
): OnboardingStep[] {
  const steps: OnboardingStep[] = [
    { key: "chat", path: "/chat", navKey: "chat", variant: "default" },
  ];
  if (navAllowed(user, "experts")) {
    steps.push({
      key: "experts",
      path: "/experts",
      navKey: "experts",
      variant: "default",
    });
  }
  steps.push(
    navAllowed(user, "models")
      ? {
          key: "models",
          path: "/admin/models",
          navKey: "models",
          variant: "default",
        }
      : { key: "models", path: "/chat", navKey: "chat", variant: "member" },
  );
  if (navAllowed(user, "channels")) {
    steps.push({
      key: "channels",
      path: "/personalization/channels",
      navKey: "channels",
      variant: "default",
    });
  }
  if (navAllowed(user, "knowledge-bases")) {
    steps.push({
      key: "knowledgeBases",
      path: "/knowledge-bases",
      navKey: "knowledge-bases",
      variant: "default",
    });
  }
  if (navAllowed(user, "skill-packages")) {
    steps.push({
      key: "skillPackages",
      path: "/skill-packages",
      navKey: "skill-packages",
      variant: "default",
    });
  }
  return steps;
}
