import assert from "node:assert/strict";
import { join } from "node:path";
import { test } from "node:test";

import { buildSidecarEnv } from "./process-tree";

/**
 * Desktop builds carry no account system, so the sidecar env has to pin the
 * setup-password gate off. The access-token TTL stays at the server default:
 * the shell renews sessions with a device credential instead of a long token.
 */

function env(overrides: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  return buildSidecarEnv(
    { PATH: "/usr/bin", OCTOP_PORT: "1", OCTOP_REQUIRE_SETUP_PASSWORD: "1", ...overrides },
    { octopHome: "/tmp/home", portableDir: "/tmp/portable", port: 51234, bindHost: "127.0.0.1" },
  );
}

test("buildSidecarEnv disables the wizard password gate", () => {
  assert.equal(env().OCTOP_REQUIRE_SETUP_PASSWORD, "0");
});

test("buildSidecarEnv leaves the access token TTL to the server", () => {
  assert.equal(env().OCTOP_ACCESS_TOKEN_TTL, undefined);
});

test("buildSidecarEnv keeps the identity and loopback pins", () => {
  const built = env();
  assert.equal(built.OCTOP_DESKTOP_SHELL, "1");
  assert.equal(built.OCTOP_HOME, "/tmp/home");
  // Built with node:path, so the separator follows the host.
  assert.equal(built.OCTOP_GREEN_PACKAGES, join("/tmp/portable", "packages"));
  assert.equal(built.OCTOP_BIND_HOST, "127.0.0.1");
  assert.equal(built.OCTOP_PORT, "51234");
  assert.equal(built.PYTHONNOUSERSITE, "1");
  assert.equal(built.PATH, "/usr/bin");
});

test("buildSidecarEnv drops an inherited PYTHONPATH", () => {
  assert.equal(env({ PYTHONPATH: "/opt/site-packages" }).PYTHONPATH, undefined);
});
