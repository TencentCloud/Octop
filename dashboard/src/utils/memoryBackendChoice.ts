export const MEMORY_BACKEND_CHOICES = ["follow", "sqlite", "postgres"] as const;

export type MemoryBackendChoice = (typeof MEMORY_BACKEND_CHOICES)[number];

export function isMemoryBackendChoice(
  value: unknown,
): value is MemoryBackendChoice {
  return (
    value === "follow" || value === "sqlite" || value === "postgres"
  );
}

export function parseMemoryBackendChoice(
  config: Record<string, unknown> | null | undefined,
): MemoryBackendChoice {
  const memory = config?.memory;
  if (!memory || typeof memory !== "object") return "follow";
  const backend = (memory as { backend?: unknown }).backend;
  if (!backend || typeof backend !== "object") return "follow";
  const type = String(
    (backend as { type?: unknown }).type || "",
  ).trim().toLowerCase();
  if (type === "sqlite") return "sqlite";
  if (type === "postgres") return "postgres";
  return "follow";
}

export interface PostgresMemoryFields {
  host?: string;
  port?: number;
  database?: string;
  user?: string;
  password?: string;
}

export function buildPostgresMemoryDsn(
  fields: PostgresMemoryFields,
): string | undefined {
  const host = fields.host?.trim();
  const database = fields.database?.trim();
  const user = fields.user?.trim();
  if (!host || !database || !user) return undefined;
  const port = Number.isFinite(fields.port) ? Number(fields.port) : 5432;
  const userEnc = encodeURIComponent(user);
  const auth = fields.password
    ? `${userEnc}:${encodeURIComponent(fields.password)}`
    : userEnc;
  return `postgresql://${auth}@${host}:${port}/${database}`;
}

export function memoryPostgresDsnFromForm(values: {
  memory_pg_host?: string;
  memory_pg_port?: number;
  memory_pg_database?: string;
  memory_pg_user?: string;
  memory_pg_password?: string;
}): string | undefined {
  return buildPostgresMemoryDsn({
    host: values.memory_pg_host,
    port: values.memory_pg_port,
    database: values.memory_pg_database,
    user: values.memory_pg_user,
    password: values.memory_pg_password,
  });
}

export function storedPostgresDsn(
  config: Record<string, unknown> | null | undefined,
): string | undefined {
  const memory = config?.memory;
  if (!memory || typeof memory !== "object") return undefined;
  const backend = (memory as { backend?: unknown }).backend;
  if (!backend || typeof backend !== "object") return undefined;
  const dsn = (backend as { dsn?: unknown }).dsn;
  return typeof dsn === "string" && dsn.trim() ? dsn.trim() : undefined;
}

export function parsePostgresMemoryDsn(
  dsn: string | undefined | null,
): PostgresMemoryFields | undefined {
  const text = dsn?.trim();
  if (!text) return undefined;
  try {
    const url = new URL(text);
    if (url.protocol !== "postgres:" && url.protocol !== "postgresql:") {
      return undefined;
    }
    const database = decodeURIComponent(url.pathname.replace(/^\//, ""));
    const user = decodeURIComponent(url.username || "");
    if (!url.hostname || !database || !user) return undefined;
    return {
      host: url.hostname,
      port: url.port ? Number(url.port) : 5432,
      database,
      user,
    };
  } catch {
    return undefined;
  }
}

export function postgresFormMatchesStored(
  values: {
    memory_pg_host?: string;
    memory_pg_port?: number;
    memory_pg_database?: string;
    memory_pg_user?: string;
    memory_pg_password?: string;
  },
  storedDsn: string | undefined,
): boolean {
  const stored = parsePostgresMemoryDsn(storedDsn);
  if (!stored) return false;
  const port = Number.isFinite(values.memory_pg_port)
    ? Number(values.memory_pg_port)
    : 5432;
  return (
    (values.memory_pg_host?.trim() || "") === (stored.host || "") &&
    port === (stored.port ?? 5432) &&
    (values.memory_pg_database?.trim() || "") === (stored.database || "") &&
    (values.memory_pg_user?.trim() || "") === (stored.user || "") &&
    !values.memory_pg_password
  );
}

export function applyMemoryBackendChoice(
  config: Record<string, unknown>,
  choice: MemoryBackendChoice,
  options?: { dsn?: string },
): Record<string, unknown> {
  const next = { ...config };
  const memory = {
    ...(typeof next.memory === "object" && next.memory
      ? (next.memory as Record<string, unknown>)
      : {}),
  };
  const dsn = options?.dsn?.trim() ?? "";
  if (choice === "follow") {
    delete memory.backend;
  } else if (choice === "sqlite") {
    memory.backend = { type: "sqlite" };
  } else if (dsn) {
    memory.backend = { type: "postgres", dsn };
  } else {
    const current =
      typeof memory.backend === "object" && memory.backend
        ? (memory.backend as Record<string, unknown>)
        : {};
    const currentType = String(current.type || "")
      .trim()
      .toLowerCase();
    if (
      currentType === "postgres" &&
      (current.dsn || current.use_control_plane_dsn)
    ) {
      memory.backend = { ...current };
    } else {
      memory.backend = { type: "postgres", use_control_plane_dsn: true };
    }
  }
  if (Object.keys(memory).length) next.memory = memory;
  else delete next.memory;
  return next;
}
