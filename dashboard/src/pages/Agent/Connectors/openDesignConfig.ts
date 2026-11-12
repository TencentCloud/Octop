export interface OpenDesignLaunchConfig {
  command: string;
  args: string[];
  env: Record<string, string>;
}

export function parseOpenDesignConfigs(
  text: string,
): Record<string, OpenDesignLaunchConfig> {
  const raw = JSON.parse(text);
  if (!raw || typeof raw !== "object" || Array.isArray(raw))
    throw new Error("config");
  const entries = raw.command
    ? { "open-design": raw }
    : raw.mcpServers ?? raw.mcp;
  if (!entries || typeof entries !== "object" || Array.isArray(entries))
    throw new Error("config");
  const result: Record<string, OpenDesignLaunchConfig> = {};
  for (const [name, value] of Object.entries(entries)) {
    if (!value || typeof value !== "object" || Array.isArray(value))
      throw new Error("config");
    const spec = value as Record<string, unknown>;
    const argv = Array.isArray(spec.command)
      ? spec.command
      : [spec.command, ...(Array.isArray(spec.args) ? spec.args : [])];
    const env = spec.env ?? spec.environment ?? {};
    if (
      !argv.length ||
      !argv.every((v) => typeof v === "string") ||
      !String(argv[0]).trim() ||
      (spec.args !== undefined && !Array.isArray(spec.args)) ||
      !env ||
      typeof env !== "object" ||
      Array.isArray(env) ||
      !Object.values(env).every((v) => typeof v === "string")
    )
      throw new Error("config");
    result[name] = {
      command: argv[0],
      args: argv.slice(1),
      env: env as Record<string, string>,
    };
  }
  if (!Object.keys(result).length) throw new Error("config");
  return result;
}
