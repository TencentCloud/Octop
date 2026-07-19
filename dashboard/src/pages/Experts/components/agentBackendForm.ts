import { request } from "../../../api/request";

export const BUILTIN_BACKENDS = ["local_shell", "filesystem", "state"] as const;
export const DEFAULT_BACKEND: BuiltinBackend = "local_shell";
export type BuiltinBackend = (typeof BUILTIN_BACKENDS)[number];
export type BackendChoice = BuiltinBackend | "composite" | `named:${string}`;

export interface PathMapping {
  path: string;
  backend: string;
}

export interface BackendOption {
  id: number;
  name: string;
  kind: string;
  enabled: boolean;
  bucket?: string | null;
}

export function isNamedBackend(ref: string): ref is `named:${string}` {
  return ref.startsWith("named:");
}

export function backendRefToSpec(
  ref: string,
  rootDir?: string,
): Record<string, unknown> {
  if (isNamedBackend(ref)) {
    return { type: "named", name: ref.slice("named:".length) };
  }
  if (ref === "state") {
    return { type: "state" };
  }
  if (ref === "local_shell" || ref === "filesystem") {
    return { type: ref, virtual_mode: true, root_dir: rootDir ?? "/" };
  }
  return { type: ref, virtual_mode: true };
}

export function isValidCompositePath(path: string): boolean {
  const trimmed = path.trim();
  return trimmed.length > 0 && trimmed.startsWith("/") && trimmed !== "/";
}

export function needsRootDirProbe(choice: string): boolean {
  return choice === "local_shell" || choice === "filesystem";
}

export type RootDirProbeCode =
  | "not_directory"
  | "permission_denied"
  | "write_failed"
  | "not_allowed";

export interface RootDirProbeResult {
  ok: boolean;
  code?: RootDirProbeCode;
  detail?: string;
  path?: string;
}

export function shouldProbeRootDir(choice: string, rootDir?: string): boolean {
  if (!needsRootDirProbe(choice)) return false;
  const normalized = (rootDir?.trim() || "/").replace(/\/+$/, "") || "/";
  return normalized !== "/";
}

export async function probeRootDir(path: string): Promise<RootDirProbeResult> {
  return request<RootDirProbeResult>("/filesystem/probe", {
    method: "POST",
    body: JSON.stringify({ path: path.trim() || "/" }),
  });
}

export function rootDirProbeMessage(
  result: RootDirProbeResult,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (result.ok) return "";
  const code = result.code ?? "write_failed";
  const key = `experts.rootDirProbe.${code}`;
  return t(key, { detail: result.detail ?? "" });
}

export function validatePathMappings(
  mappings: PathMapping[],
  t: (key: string) => string,
): string | null {
  for (const mapping of mappings) {
    if (!mapping.backend) continue;
    const trimmed = mapping.path.trim();
    if (!trimmed) return t("experts.backendModes.pathInvalidRoot");
    if (trimmed === "/" || !trimmed.startsWith("/")) {
      return t("experts.backendModes.pathInvalidRoot");
    }
  }
  return null;
}

export function buildBackendSpec(
  choice: string,
  compositeDefault: string,
  pathMappings: PathMapping[],
  rootDir?: string,
): Record<string, unknown> {
  if (choice === "composite") {
    const routes: Record<string, unknown> = {};
    for (const mapping of pathMappings) {
      if (!isValidCompositePath(mapping.path) || !mapping.backend) continue;
      routes[mapping.path.trim()] = backendRefToSpec(mapping.backend);
    }
    return {
      type: "composite",
      default: backendRefToSpec(compositeDefault),
      routes,
    };
  }
  return backendRefToSpec(choice, rootDir);
}

function specToBackendRef(spec: Record<string, unknown>): string {
  const type = String(spec.type ?? "");
  if (type === "named") {
    const name = spec.name;
    return typeof name === "string" ? `named:${name}` : DEFAULT_BACKEND;
  }
  if (BUILTIN_BACKENDS.includes(type as BuiltinBackend)) {
    return type;
  }
  return DEFAULT_BACKEND;
}

export function parseBackendSpec(spec: unknown): {
  backendChoice: string;
  compositeDefault: string;
  pathMappings: PathMapping[];
  rootDir: string;
} {
  if (!spec || typeof spec !== "object" || Array.isArray(spec)) {
    return {
      backendChoice: DEFAULT_BACKEND,
      compositeDefault: DEFAULT_BACKEND,
      pathMappings: [],
      rootDir: "/",
    };
  }
  const obj = spec as Record<string, unknown>;
  const rootDir = typeof obj.root_dir === "string" ? obj.root_dir : "/";
  if (obj.type !== "composite") {
    return {
      backendChoice: specToBackendRef(obj),
      compositeDefault: DEFAULT_BACKEND,
      pathMappings: [],
      rootDir,
    };
  }
  const defaultSpec = obj.default;
  const compositeDefault =
    defaultSpec &&
    typeof defaultSpec === "object" &&
    !Array.isArray(defaultSpec)
      ? specToBackendRef(defaultSpec as Record<string, unknown>)
      : DEFAULT_BACKEND;
  const routes = obj.routes;
  const pathMappings: PathMapping[] = [];
  if (routes && typeof routes === "object" && !Array.isArray(routes)) {
    for (const [path, routeSpec] of Object.entries(routes)) {
      if (
        routeSpec &&
        typeof routeSpec === "object" &&
        !Array.isArray(routeSpec)
      ) {
        pathMappings.push({
          path,
          backend: specToBackendRef(routeSpec as Record<string, unknown>),
        });
      }
    }
  }
  return {
    backendChoice: "composite",
    compositeDefault,
    pathMappings,
    rootDir: "/",
  };
}

export function builtinLabel(
  mode: BuiltinBackend,
  t: (key: string) => string,
): string {
  const keys: Record<BuiltinBackend, string> = {
    local_shell: "experts.backendModes.localShell",
    filesystem: "experts.backendModes.filesystem",
    state: "experts.backendModes.state",
  };
  return t(keys[mode]);
}

export function builtinDesc(
  mode: string,
  t: (key: string) => string,
): { text: string; warning?: string } | null {
  if (mode === "composite")
    return { text: t("experts.backendModes.compositeDesc") };
  if (isNamedBackend(mode)) return null;
  const keys: Record<string, string> = {
    local_shell: "experts.backendModes.localShellDesc",
    filesystem: "experts.backendModes.filesystemDesc",
    state: "experts.backendModes.stateDesc",
  };
  if (!keys[mode]) return null;
  const result: { text: string; warning?: string } = { text: t(keys[mode]) };
  if (mode === "local_shell") {
    result.warning = t("experts.backendModes.localShellWarning");
  }
  return result;
}
