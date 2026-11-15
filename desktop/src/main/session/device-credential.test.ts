import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  DEVICE_CREDENTIAL_FILE,
  DEVICE_CREDENTIAL_MODE,
  DeviceCredentialStore,
  type CredentialCipher,
} from "./device-credential";

/**
 * The device credential is the only thing standing between a desktop install
 * and a login screen nobody can fill in, so the store has to survive a
 * missing/corrupt file, a host without a keychain, and an OS umask that would
 * otherwise hand the file to other users.
 */

function workingCipher(): CredentialCipher {
  // Reversible stand-in for safeStorage: the point is that the on-disk value is
  // not the plaintext, not that the transform is cryptography.
  return {
    available: async () => true,
    encrypt: async (plain) => `enc:${Buffer.from(plain, "utf8").toString("base64")}`,
    decrypt: async (payload) => {
      if (!payload.startsWith("enc:")) throw new Error("bad ciphertext");
      return Buffer.from(payload.slice(4), "base64").toString("utf8");
    },
  };
}

function missingCipher(): CredentialCipher {
  return {
    available: async () => false,
    encrypt: async () => {
      throw new Error("encryption unavailable");
    },
    decrypt: async () => {
      throw new Error("encryption unavailable");
    },
  };
}

async function tempHome(): Promise<string> {
  return fs.mkdtemp(join(tmpdir(), "octop-credential-"));
}

test("getOrCreate mints a secret once and reuses it afterwards", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, workingCipher());

  const first = await store.getOrCreate();
  assert.equal(first.created, true);
  assert.ok(first.secret.length >= 32, "server requires at least 32 characters");

  const second = await store.getOrCreate();
  assert.equal(second.created, false);
  assert.equal(second.secret, first.secret);

  await fs.rm(home, { recursive: true, force: true });
});

test("the stored file is owner-only and does not hold the plaintext", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, workingCipher());
  const { secret } = await store.getOrCreate();

  const file = join(home, DEVICE_CREDENTIAL_FILE);
  const stat = await fs.stat(file);
  // Windows has no POSIX permission bits — Node reports 0o666 for every file, so
  // there is nothing to assert and nothing the product can enforce that way.
  if (process.platform !== "win32") {
    assert.equal(stat.mode & 0o777, DEVICE_CREDENTIAL_MODE);
  }

  const raw = await fs.readFile(file, "utf8");
  assert.ok(!raw.includes(secret), "secret must be encrypted at rest");
  const parsed = JSON.parse(raw) as { v: number; encrypted: boolean };
  assert.equal(parsed.v, 1);
  assert.equal(parsed.encrypted, true);

  await fs.rm(home, { recursive: true, force: true });
});

test("a host without a keychain keeps the secret in memory and writes nothing", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, missingCipher());

  const { secret, created } = await store.getOrCreate();
  assert.equal(created, true);
  // Renewal still works for this launch…
  assert.equal(await store.read(), secret);
  // …but nothing reusable ever reaches the disk.
  await assert.rejects(fs.stat(join(home, DEVICE_CREDENTIAL_FILE)), /ENOENT/);

  await fs.rm(home, { recursive: true, force: true });
});

test("the in-memory secret does not survive a restart", async () => {
  const home = await tempHome();
  await new DeviceCredentialStore(home, missingCipher()).getOrCreate();

  const nextLaunch = new DeviceCredentialStore(home, missingCipher());
  assert.equal(await nextLaunch.read(), null);
  // A fresh launch mints a new secret rather than failing outright.
  assert.equal((await nextLaunch.getOrCreate()).created, true);

  await fs.rm(home, { recursive: true, force: true });
});

test("a v1 plaintext file is not a credential until migrate() adopts it", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, workingCipher());
  await fs.writeFile(
    join(home, DEVICE_CREDENTIAL_FILE),
    JSON.stringify({ v: 1, encrypted: false, secret: "legacy-secret" }),
    "utf8",
  );

  assert.equal(await store.read(), null);

  await fs.rm(home, { recursive: true, force: true });
});

test("migrate re-encrypts a v1 plaintext file when a keychain is available", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, workingCipher());
  await fs.writeFile(
    join(home, DEVICE_CREDENTIAL_FILE),
    JSON.stringify({ v: 1, encrypted: false, secret: "legacy-secret" }),
    "utf8",
  );

  await store.migrate();

  const raw = await fs.readFile(join(home, DEVICE_CREDENTIAL_FILE), "utf8");
  assert.ok(!raw.includes("legacy-secret"), "the plaintext must not survive the upgrade");
  assert.equal((JSON.parse(raw) as { encrypted: boolean }).encrypted, true);
  assert.equal(await store.read(), "legacy-secret");

  await fs.rm(home, { recursive: true, force: true });
});

test("migrate adopts and deletes a v1 plaintext file when there is no keychain", async () => {
  const home = await tempHome();
  const file = join(home, DEVICE_CREDENTIAL_FILE);
  await fs.writeFile(file, JSON.stringify({ v: 1, encrypted: false, secret: "legacy-secret" }), "utf8");

  const store = new DeviceCredentialStore(home, missingCipher());
  await store.migrate();

  await assert.rejects(fs.stat(file), /ENOENT/);
  // The adopted secret keeps this launch signed in, then goes away with it.
  assert.equal(await store.read(), "legacy-secret");
  assert.equal(await new DeviceCredentialStore(home, missingCipher()).read(), null);

  await fs.rm(home, { recursive: true, force: true });
});

test("migrate drops a credential file with no usable secret", async () => {
  const home = await tempHome();
  const file = join(home, DEVICE_CREDENTIAL_FILE);
  await fs.writeFile(file, JSON.stringify({ v: 1, encrypted: false, secret: "" }), "utf8");

  await new DeviceCredentialStore(home, missingCipher()).migrate();

  await assert.rejects(fs.stat(file), /ENOENT/);

  await fs.rm(home, { recursive: true, force: true });
});

test("read returns null when the file is missing or corrupt", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, workingCipher());

  assert.equal(await store.read(), null);

  await fs.writeFile(join(home, DEVICE_CREDENTIAL_FILE), "{not json", "utf8");
  assert.equal(await store.read(), null);

  await fs.writeFile(
    join(home, DEVICE_CREDENTIAL_FILE),
    JSON.stringify({ v: 1, encrypted: true, secret: "" }),
    "utf8",
  );
  assert.equal(await store.read(), null);

  await fs.rm(home, { recursive: true, force: true });
});

test("an encrypted credential is unreadable without the keychain", async () => {
  const home = await tempHome();
  const written = new DeviceCredentialStore(home, workingCipher());
  await written.getOrCreate();

  // Same file, different host state: the keychain went away (or the file was
  // copied from another machine), so the shell must treat it as absent.
  const reopened = new DeviceCredentialStore(home, missingCipher());
  assert.equal(await reopened.read(), null);

  await fs.rm(home, { recursive: true, force: true });
});

test("clear forces a fresh secret on the next call", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, workingCipher());
  const first = await store.getOrCreate();

  await store.clear();
  assert.equal(await store.read(), null);

  const again = await store.getOrCreate();
  assert.equal(again.created, true);
  assert.notEqual(again.secret, first.secret);

  await fs.rm(home, { recursive: true, force: true });
});

test("a temporarily unusable keychain does not destroy the stored ciphertext", async () => {
  const home = await tempHome();
  const original = await new DeviceCredentialStore(home, workingCipher()).getOrCreate();

  // Keychain locked or absent for this launch: renewal falls back to a new
  // in-memory secret, but the file that the next launch could use stays put.
  const locked = new DeviceCredentialStore(home, missingCipher());
  const fallback = await locked.getOrCreate();
  assert.notEqual(fallback.secret, original.secret);
  await fs.stat(join(home, DEVICE_CREDENTIAL_FILE));

  assert.equal(await new DeviceCredentialStore(home, workingCipher()).read(), original.secret);

  await fs.rm(home, { recursive: true, force: true });
});

test("clear forgets an in-memory credential too", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, missingCipher());
  await store.getOrCreate();

  await store.clear();
  assert.equal(await store.read(), null);

  await fs.rm(home, { recursive: true, force: true });
});

test("write creates the data root when it does not exist yet", async () => {
  const home = join(await tempHome(), "nested", "data");
  const store = new DeviceCredentialStore(home, workingCipher());

  await store.write("explicit-secret");
  assert.equal(await store.read(), "explicit-secret");

  await fs.rm(join(home, "..", ".."), { recursive: true, force: true });
});
