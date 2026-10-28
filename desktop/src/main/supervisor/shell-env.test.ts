import assert from "node:assert/strict";
import { join, resolve, sep } from "node:path";
import { test } from "node:test";

import { resolveOctopHome, expandHome } from "./shell-env";
import { resolveStaticPath, isExternalLink } from "../protocol/static-handler";
import { isApiPath, toBackendUrl, sanitizeForwardHeaders } from "../protocol/stream-proxy";

/**
 * The fixtures are POSIX-shaped on purpose (a home directory, a URL path), but
 * the functions under test would build paths with `node:path`, so every expected
 * value has to go through `join`/`resolve` too — otherwise the suite only passes
 * on the machine it was written on.
 */

/**
 * `resolveStaticPath` receives its root from `app.getAppPath()`, which is always
 * host-shaped. Feeding it a POSIX root on Windows is not a case that can happen:
 * `path.resolve("/root/dashboard", "assets/app.js")` lands on the current drive
 * root and the confinement check then — correctly — refuses it.
 */
const DASHBOARD_ROOT = resolve(sep, "root", "dashboard");

test("resolveOctopHome prefers inherited non-empty value", () => {
  assert.equal(
    resolveOctopHome({ OCTOP_HOME: " /data/octop " }, {}, "/home/u"),
    "/data/octop",
  );
});

test("resolveOctopHome falls back to login shell then ~/.octop", () => {
  assert.equal(resolveOctopHome({}, { OCTOP_HOME: "/from/shell" }, "/home/u"), "/from/shell");
  assert.equal(resolveOctopHome({}, {}, "/home/u"), join("/home/u", ".octop"));
});

test("expandHome expands leading tilde", () => {
  assert.equal(expandHome("~/octop", "/home/u"), join("/home/u", "octop"));
  assert.equal(expandHome("~", "/home/u"), "/home/u");
  assert.equal(expandHome("/abs/path", "/home/u"), "/abs/path");
});

test("resolveStaticPath confines to root", () => {
  assert.equal(
    resolveStaticPath(DASHBOARD_ROOT, "/assets/app.js"),
    join(DASHBOARD_ROOT, "assets", "app.js"),
  );
  assert.equal(resolveStaticPath(DASHBOARD_ROOT, "/"), join(DASHBOARD_ROOT, "index.html"));
  assert.equal(resolveStaticPath(DASHBOARD_ROOT, "/sub/"), join(DASHBOARD_ROOT, "sub", "index.html"));
  assert.equal(resolveStaticPath(DASHBOARD_ROOT, "/../../etc/passwd"), null);
  assert.equal(resolveStaticPath(DASHBOARD_ROOT, "/sub/../../etc/passwd"), null);
});

test("isExternalLink only allows real http(s) links", () => {
  assert.equal(isExternalLink("https://octop.cloud/docs"), true);
  assert.equal(isExternalLink("http://127.0.0.1:1234/api"), false);
  assert.equal(isExternalLink("octop://app/api/health"), false);
});

test("api path + backend url mapping", () => {
  assert.equal(isApiPath("/api/health"), true);
  assert.equal(isApiPath("/assets/app.js"), false);
  assert.equal(toBackendUrl(4321, "/api/health", ""), "http://127.0.0.1:4321/api/health");
  assert.equal(toBackendUrl(4321, "/api/agents", "?q=1"), "http://127.0.0.1:4321/api/agents?q=1");
});

test("sanitizeForwardHeaders strips connection-level headers", () => {
  const h = new Headers({
    Host: "evil.example",
    Authorization: "Bearer keep",
    Connection: "keep-alive",
    Cookie: "session=abc",
  });
  const out = sanitizeForwardHeaders(h);
  assert.equal("host" in out, false);
  assert.equal("cookie" in out, false);
  assert.equal("connection" in out, false);
  assert.equal(out["authorization"], "Bearer keep");
});
