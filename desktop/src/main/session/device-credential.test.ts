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
    available: () => true,
    encrypt: (plain) => `enc:${Buffer.from(plain, "utf8").toString("base64")}`,
    decrypt: (payload) => {
      if (!payload.startsWith("enc:")) throw new Error("bad ciphertext");
      return Buffer.from(payload.slice(4), "base64").toString("utf8");
    },
  };
}

function missingCipher(): CredentialCipher {
  return {
    available: () => false,
    encrypt: () => {
      throw new Error("encryption unavailable");
    },
    decrypt: () => {
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
  assert.equal(stat.mode & 0o777, DEVICE_CREDENTIAL_MODE);

  const raw = await fs.readFile(file, "utf8");
  assert.ok(!raw.includes(secret), "secret must be encrypted at rest");
  const parsed = JSON.parse(raw) as { v: number; encrypted: boolean };
  assert.equal(parsed.v, 1);
  assert.equal(parsed.encrypted, true);

  await fs.rm(home, { recursive: true, force: true });
});

test("a host without a keychain stores the secret as-is", async () => {
  const home = await tempHome();
  const store = new DeviceCredentialStore(home, missingCipher());

  const { secret } = await store.getOrCreate();
  const raw = await fs.readFile(join(home, DEVICE_CREDENTIAL_FILE), "utf8");
  assert.equal((JSON.parse(raw) as { encrypted: boolean }).encrypted, false);
  assert.equal(await store.read(), secret);

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

test("write creates the data root when it does not exist yet", async () => {
  const home = join(await tempHome(), "nested", "data");
  const store = new DeviceCredentialStore(home, workingCipher());

  await store.write("explicit-secret");
  assert.equal(await store.read(), "explicit-secret");

  await fs.rm(join(home, "..", ".."), { recursive: true, force: true });
});
