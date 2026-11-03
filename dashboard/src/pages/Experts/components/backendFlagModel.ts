import { isNamedBackend, parseBackendSpec } from "./agentBackendForm";

export interface BackendFlagModel {
  /** Storage-page logo kind, when one exists. */
  logoKind: string | null;
  /** Lucide fallback when there is no brand mark. */
  fallback: "state" | "composite" | "generic" | null;
  /** Built-in mode label (``experts.backendModes.*``). */
  labelKey: string | null;
  /** Configured storage backend name. */
  labelText: string | null;
}

const BUILTIN_FLAGS: Record<
  string,
  Pick<BackendFlagModel, "logoKind" | "fallback" | "labelKey">
> = {
  local_shell: {
    logoKind: "shell",
    fallback: null,
    labelKey: "experts.backendModes.localShell",
  },
  filesystem: {
    logoKind: "filesystem",
    fallback: null,
    labelKey: "experts.backendModes.filesystem",
  },
  state: {
    logoKind: null,
    fallback: "state",
    labelKey: "experts.backendModes.state",
  },
  composite: {
    logoKind: null,
    fallback: "composite",
    labelKey: "experts.backendModes.composite",
  },
};

export type BackendFlagIcon =
  | "shell"
  | "filesystem"
  | "database"
  | "storage"
  | "sandbox"
  | "state"
  | "composite"
  | "generic";

const DATABASE_KINDS = new Set(["postgres"]);
const STORAGE_KINDS = new Set(["cos", "s3", "oss", "obs", "custom"]);
const SANDBOX_KINDS = new Set(["docker", "opensandbox"]);

/** Collapse a concrete backend into one of the shared flag icons. */
export function backendFlagIcon(model: BackendFlagModel): BackendFlagIcon {
  const kind = (model.logoKind ?? model.fallback ?? "generic").toLowerCase();
  if (kind === "shell" || kind === "local_shell") return "shell";
  if (kind === "filesystem") return "filesystem";
  if (DATABASE_KINDS.has(kind)) return "database";
  if (STORAGE_KINDS.has(kind)) return "storage";
  if (SANDBOX_KINDS.has(kind)) return "sandbox";
  if (kind === "state" || kind === "composite") return kind;
  return "generic";
}

function fromChoice(
  choice: string,
  backends: ReadonlyArray<{ name: string; kind: string }>,
): BackendFlagModel {
  if (isNamedBackend(choice)) {
    const name = choice.slice("named:".length);
    const kind = backends.find((row) => row.name === name)?.kind ?? null;
    return {
      logoKind: kind,
      fallback: kind ? null : "generic",
      labelKey: null,
      labelText: name,
    };
  }
  const known = BUILTIN_FLAGS[choice];
  if (known) {
    return { ...known, labelText: null };
  }
  return {
    logoKind: null,
    fallback: "generic",
    labelKey: null,
    labelText: choice,
  };
}

/**
 * Icon + tooltip for an expert's storage backend.
 *
 * Missing specs become the local-shell default when ``assumeDefault`` is set.
 * That matches both a local expert and a peer expert with no explicit backend.
 */
export function resolveBackendFlag(
  spec: unknown,
  backends: ReadonlyArray<{ name: string; kind: string }>,
  options?: { assumeDefault?: boolean },
): BackendFlagModel | null {
  const assumeDefault = options?.assumeDefault !== false;
  if (spec == null) {
    if (!assumeDefault) return null;
    return fromChoice("local_shell", backends);
  }
  return fromChoice(parseBackendSpec(spec).backendChoice, backends);
}
