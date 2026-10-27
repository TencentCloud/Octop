import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveOctopHome, expandHome } from "./shell-env";
import { resolveStaticPath, isExternalLink } from "../protocol/static-handler";
import { isApiPath, toBackendUrl, sanitizeForwardHeaders } from "../protocol/stream-proxy";

test("resolveOctopHome prefers inherited non-empty value", () => {
  assert.equal(
    resolveOctopHome({ OCTOP_HOME: " /data/octop " }, {}, "/home/u"),
    "/data/octop",
  );
});

test("resolveOctopHome falls back to login shell then ~/.octop", () => {
  assert.equal(resolveOctopHome({}, { OCTOP_HOME: "/from/shell" }, "/home/u"), "/from/shell");
  assert.equal(resolveOctopHome({}, {}, "/home/u"), "/home/u/.octop");
});

test("expandHome expands leading tilde", () => {
  assert.equal(expandHome("~/octop", "/home/u"), "/home/u/octop");
  assert.equal(expandHome("~", "/home/u"), "/home/u");
  assert.equal(expandHome("/abs/path", "/home/u"), "/abs/path");
});

test("resolveStaticPath confines to root", () => {
  assert.equal(resolveStaticPath("/root/dashboard", "/assets/app.js"), "/root/dashboard/assets/app.js");
  assert.equal(resolveStaticPath("/root/dashboard", "/"), "/root/dashboard/index.html");
  assert.equal(resolveStaticPath("/root/dashboard", "/../../etc/passwd"), null);
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
