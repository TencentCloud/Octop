#!/usr/bin/env node
// DSH-only target resolution for the memory hooks.
//
// The installer writes `config.json` next to the scripts, but a DSH whose MCP
// panel already knows the octop server needs no second copy of the credentials.
// Precedence: environment -> `config.json` -> the `octop-memory*` entry of this
// DSH's own MCP server table (`$DSH_HOME/storages/mcp_servers.json`), enabled
// servers first, then prod, local, oauth. `OCTOP_MEMORY_SERVER` names one entry
// explicitly and may pick a disabled one.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { loadConfig } from "../lib/octop-memory-client.mjs";

const ENV_VAR_NAME = /^[A-Z][A-Z0-9_]*$/;

function serverTablePath() {
  const home = process.env.DSH_HOME || path.join(os.homedir(), ".dsh");
  return path.join(home, "storages", "mcp_servers.json");
}

/** A bare env-var name resolves from the environment. */
function headerValue(value) {
  const text = String(value ?? "").trim();
  if (ENV_VAR_NAME.test(text) && process.env[text]) return process.env[text];
  return text;
}

function headerMap(server) {
  const headers = {};
  for (const item of Array.isArray(server.headers) ? server.headers : []) {
    if (item && typeof item.name === "string" && item.name) headers[item.name] = headerValue(item.value);
  }
  return headers;
}

function rank(server) {
  const name = String(server.serverName ?? "").toLowerCase();
  if (name === "octop-memory-prod") return 10;
  if (name === "octop-memory" || name === "octop-memory-local") return 20;
  if (name === "octop-memory-oauth") return 30;
  return 40;
}

function configFromServer(server) {
  const headers = headerMap(server);
  const names = Object.keys(headers);
  const tokenHeader =
    names.find((name) => name.toLowerCase() === "authorization") ??
    names.find((name) => name.toLowerCase() === "x-octop-memory-token") ??
    "";
  return {
    endpoint: String(server.url ?? "").trim(),
    token: tokenHeader ? headers[tokenHeader].replace(/^Bearer\s+/i, "") : "",
    tokenHeader,
    agentId: headers["X-Octop-Agent-Id"] ?? "",
    userId: headers["X-Octop-User-Id"] ?? "",
  };
}

/** The usable octop entry of this DSH's MCP server table, or null. */
export function discoverConfig() {
  let servers;
  try {
    const parsed = JSON.parse(fs.readFileSync(serverTablePath(), "utf8"));
    servers = Object.values(parsed?.tables?.servers ?? {});
  } catch {
    return null; // no DSH storage here -> nothing to discover
  }
  const wanted = (process.env.OCTOP_MEMORY_SERVER || "").trim().toLowerCase();
  const candidates = servers
    .filter((server) => server && typeof server === "object" && !server.stale)
    .filter((server) => /^octop[-_]?memory/i.test(String(server.serverName ?? "")))
    .filter((server) => !wanted || String(server.serverName ?? "").toLowerCase() === wanted)
    .sort((a, b) => (wanted ? 0 : Number(!a.enabled) - Number(!b.enabled)) || rank(a) - rank(b));
  for (const server of candidates) {
    const config = configFromServer(server);
    if (config.endpoint && config.token) return config;
  }
  return null;
}

/** What these hooks should talk to. */
export function resolveConfig() {
  const configured = loadConfig();
  if (configured.endpoint && configured.token) return configured;
  return discoverConfig() ?? configured;
}
