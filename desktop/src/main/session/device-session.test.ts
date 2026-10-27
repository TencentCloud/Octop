import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { DeviceCredentialStore } from "./device-credential";
import { DeviceSessionClient } from "./device-session";

/**
 * The renderer only ever asks the shell for a JWT. These cover the shell side of
 * that trade: what it sends, what it does with a refusal, and the fact that a
 * sidecar restart (no base URL, connection refused) degrades to "no session"
 * instead of throwing into the IPC handler.
 */

interface Call {
  url: string;
  body: unknown;
  authorization: string | undefined;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function makeFixture(options: {
  baseUrl?: string | null;
  respond?: (call: Call) => Response | Promise<Response>;
  seed?: string;
} = {}) {
  const home = await fs.mkdtemp(join(tmpdir(), "octop-session-"));
  const store = new DeviceCredentialStore(home, {
    available: async () => true,
    encrypt: async (plain) => `enc:${Buffer.from(plain, "utf8").toString("base64")}`,
    decrypt: async (payload) =>
      Buffer.from(payload.slice(4), "base64").toString("utf8"),
  });
  if (options.seed) await store.write(options.seed);

  const calls: Call[] = [];
  const fetchImpl = (async (input: string | URL | Request, init?: RequestInit) => {
    const call: Call = {
      url: String(input),
      body: init?.body ? JSON.parse(String(init.body)) : null,
      authorization: (init?.headers as Record<string, string> | undefined)
        ?.Authorization,
    };
    calls.push(call);
    if (!options.respond) throw new TypeError("fetch failed");
    return options.respond(call);
  }) as typeof fetch;

  const client = new DeviceSessionClient({
    store,
    baseUrl: () =>
      options.baseUrl === undefined ? "http://127.0.0.1:51234" : options.baseUrl,
    label: "darwin-arm64",
    fetchImpl,
  });

  return {
    store,
    client,
    calls,
    cleanup: () => fs.rm(home, { recursive: true, force: true }),
  };
}

/** Indexed access with a real assertion (the tsconfig forbids blind lookups). */
function callAt(calls: Call[], index: number): Call {
  const call = calls[index];
  assert.ok(call, `expected call #${index}`);
  return call;
}

test("register binds the credential to the current user", async () => {
  const fx = await makeFixture({ respond: () => jsonResponse(200, { ok: true }) });

  assert.equal(await fx.client.register("jwt-1"), true);
  assert.equal(fx.calls.length, 1);
  const first = callAt(fx.calls, 0);
  assert.equal(first.url, "http://127.0.0.1:51234/api/auth/device/register");
  assert.equal(first.authorization, "Bearer jwt-1");
  const body = first.body as { device_token: string; label: string };
  assert.equal(body.label, "darwin-arm64");
  // The token that goes over the wire is the stored secret, not a new one.
  assert.equal(body.device_token, await fx.store.read());

  await fx.cleanup();
});

test("register reports a refusal without discarding the credential", async () => {
  const fx = await makeFixture({ respond: () => jsonResponse(401, {}) });

  assert.equal(await fx.client.register("jwt-1"), false);
  assert.ok(await fx.store.read(), "a retry with a fresh JWT must still work");

  await fx.cleanup();
});

test("register refuses an empty access token without calling the server", async () => {
  const fx = await makeFixture({ respond: () => jsonResponse(200, {}) });

  assert.equal(await fx.client.register(""), false);
  assert.equal(fx.calls.length, 0);

  await fx.cleanup();
});

test("renew returns null when this install has no credential", async () => {
  const fx = await makeFixture({ respond: () => jsonResponse(200, {}) });

  assert.equal(await fx.client.renew(), null);
  assert.equal(fx.calls.length, 0, "no credential means no request");

  await fx.cleanup();
});

test("renew exchanges the credential for a JWT", async () => {
  const fx = await makeFixture({
    seed: "stored-secret",
    respond: () =>
      jsonResponse(200, { access_token: "fresh-jwt", expires_in: 86400 }),
  });

  assert.deepEqual(await fx.client.renew(), {
    access_token: "fresh-jwt",
    expires_in: 86400,
  });
  const call = callAt(fx.calls, 0);
  assert.equal(call.url, "http://127.0.0.1:51234/api/auth/device/token");
  assert.equal(call.authorization, undefined, "the token endpoint is unauthenticated");
  assert.deepEqual(call.body, { device_token: "stored-secret" });

  await fx.cleanup();
});

test("renew tolerates a response without expires_in", async () => {
  const fx = await makeFixture({
    seed: "stored-secret",
    respond: () => jsonResponse(200, { access_token: "fresh-jwt" }),
  });

  assert.deepEqual(await fx.client.renew(), {
    access_token: "fresh-jwt",
    expires_in: 0,
  });

  await fx.cleanup();
});

test("renew returns null on a rejected credential or a malformed body", async () => {
  const rejected = await makeFixture({
    seed: "revoked-secret",
    respond: () => jsonResponse(403, { error: { code: "AUTH_FAILED" } }),
  });
  assert.equal(await rejected.client.renew(), null);
  // The server said no, so the shell keeps the file: a later register replaces
  // it, and a transient failure must not force a re-install.
  assert.equal(await rejected.store.read(), "revoked-secret");
  await rejected.cleanup();

  const malformed = await makeFixture({
    seed: "stored-secret",
    respond: () => jsonResponse(200, { access_token: "" }),
  });
  assert.equal(await malformed.client.renew(), null);
  await malformed.cleanup();
});

test("renew and register degrade quietly while the sidecar is down", async () => {
  const noBase = await makeFixture({
    baseUrl: null,
    seed: "stored-secret",
    respond: () => jsonResponse(200, {}),
  });
  assert.equal(await noBase.client.renew(), null);
  assert.equal(await noBase.client.register("jwt-1"), false);
  assert.equal(noBase.calls.length, 0);
  await noBase.cleanup();

  const refused = await makeFixture({ seed: "stored-secret" });
  assert.equal(await refused.client.renew(), null);
  assert.equal(await refused.client.register("jwt-1"), false);
  assert.equal(refused.calls.length, 2, "both attempts were made and swallowed");
  await refused.cleanup();
});

test("revoke forgets the credential only after the server confirms", async () => {
  const failing = await makeFixture({
    seed: "stored-secret",
    respond: () => jsonResponse(500, {}),
  });
  assert.equal(await failing.client.revoke("jwt-1"), false);
  assert.equal(await failing.store.read(), "stored-secret");
  await failing.cleanup();

  const ok = await makeFixture({
    seed: "stored-secret",
    respond: () => jsonResponse(200, { ok: true }),
  });
  assert.equal(await ok.client.revoke("jwt-1"), true);
  assert.equal(await ok.store.read(), null);
  const call = callAt(ok.calls, 0);
  assert.equal(call.url, "http://127.0.0.1:51234/api/auth/device/revoke");
  assert.equal(call.authorization, "Bearer jwt-1");
  await ok.cleanup();
});
