import type {
  HitlDecisionHandler,
  HitlSessionMode,
  HitlSessionPolicy,
} from "../../../api/types/hitl";

export type { HitlDecisionHandler, HitlSessionMode, HitlSessionPolicy };

export const DEFAULT_HITL_SESSION_POLICY: HitlSessionPolicy = { mode: "ask" };

export function parseHitlSessionPolicy(value: unknown): HitlSessionPolicy {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return DEFAULT_HITL_SESSION_POLICY;
  }
  const raw = value as { mode?: unknown; tools?: unknown };
  if (raw.mode === "allow_all") {
    return { mode: "allow_all" };
  }
  if (raw.mode === "allow_tools") {
    const tools = Array.isArray(raw.tools)
      ? raw.tools.filter(
          (item): item is string =>
            typeof item === "string" && item.trim().length > 0,
        )
      : [];
    if (tools.length === 0) return DEFAULT_HITL_SESSION_POLICY;
    return { mode: "allow_tools", tools: [...new Set(tools)] };
  }
  return DEFAULT_HITL_SESSION_POLICY;
}

export function isHitlBypassPolicy(policy: HitlSessionPolicy): boolean {
  return policy.mode === "allow_all" || policy.mode === "allow_tools";
}

export function mergeAllowTools(
  current: HitlSessionPolicy,
  names: string[],
): HitlSessionPolicy {
  if (current.mode === "allow_all") return { mode: "allow_all" };
  const extra = names
    .map((name) => name.trim())
    .filter((name) => name.length > 0);
  const tools = [...new Set([...(current.tools ?? []), ...extra])];
  if (tools.length === 0) return DEFAULT_HITL_SESSION_POLICY;
  return { mode: "allow_tools", tools };
}

export function withoutAllowTools(
  current: HitlSessionPolicy,
  name: string,
): HitlSessionPolicy {
  if (current.mode !== "allow_tools") return current;
  const tools = (current.tools ?? []).filter((item) => item !== name);
  if (tools.length === 0) return DEFAULT_HITL_SESSION_POLICY;
  return { mode: "allow_tools", tools };
}
