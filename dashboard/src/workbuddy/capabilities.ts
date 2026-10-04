export type CapabilityState =
  | "available"
  | "unconfigured"
  | "unsupported"
  | "forbidden";

export interface UiCapability {
  state: CapabilityState;
  reasonKey?: string;
  configurePath?: string;
}

export function resolveUiCapability({
  supported = true,
  permitted = true,
  configured = true,
  configurePath,
}: {
  supported?: boolean;
  permitted?: boolean;
  configured?: boolean;
  configurePath?: string;
}): UiCapability {
  if (!permitted)
    return { state: "forbidden", reasonKey: "workbuddy.capability.forbidden" };
  if (!supported)
    return {
      state: "unsupported",
      reasonKey: "workbuddy.capability.unsupported",
    };
  if (!configured)
    return {
      state: "unconfigured",
      reasonKey: "workbuddy.capability.unconfigured",
      configurePath,
    };
  return { state: "available" };
}

export const DEFERRED_FEATURES = [
  {
    id: "projects",
    path: "/projects",
    sourceView: "projects",
    labelKey: "workbuddy.projects",
    descriptionKey: "workbuddy.projectsDescription",
  },
  {
    id: "space",
    path: "/space",
    sourceView: "space",
    labelKey: "workbuddy.space",
    descriptionKey: "workbuddy.spaceDescription",
  },
  {
    id: "cloud",
    path: "/cloud-service",
    sourceView: "cloud-service",
    labelKey: "workbuddy.cloud",
    descriptionKey: "workbuddy.cloudDescription",
  },
  {
    id: "genie",
    path: "/genie",
    sourceView: "genie-home",
    labelKey: "workbuddy.apps",
    descriptionKey: "workbuddy.appsDescription",
  },
  {
    id: "tencent-docs",
    path: "/library/tencent-docs",
    sourceView: "tencent-docs",
    labelKey: "workbuddy.tencentDocs",
    descriptionKey: "workbuddy.libraryDescription",
  },
  {
    id: "ima",
    path: "/library/ima",
    sourceView: "ima",
    labelKey: "workbuddy.ima",
    descriptionKey: "workbuddy.libraryDescription",
  },
  {
    id: "lexiang",
    path: "/library/lexiang",
    sourceView: "lexiang",
    labelKey: "workbuddy.lexiang",
    descriptionKey: "workbuddy.libraryDescription",
  },
  {
    id: "agent-mail",
    path: "/library/agent-mail",
    sourceView: "agent-mail",
    labelKey: "workbuddy.agentMail",
    descriptionKey: "workbuddy.mailDescription",
  },
  {
    id: "discover",
    path: "/discover",
    sourceView: "discover",
    labelKey: "workbuddy.discover",
    descriptionKey: "workbuddy.discoverDescription",
  },
  {
    id: "inspiration",
    path: "/inspiration",
    sourceView: "inspiration",
    labelKey: "workbuddy.inspiration",
    descriptionKey: "workbuddy.inspirationDescription",
  },
] as const;

export type DeferredFeatureId = (typeof DEFERRED_FEATURES)[number]["id"];
