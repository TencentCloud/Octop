import { randomBytes } from "node:crypto";
import { promises as fs } from "node:fs";
import { join } from "node:path";

/**
 * Per-install device credential (§7 accounts).
 *
 * Desktop builds have no password a user could type, so the shell keeps a
 * secret it can trade for a fresh JWT when the old one expired. It lives in the
 * data root next to the database, encrypted with the OS keychain
 * (`safeStorage`), and is never handed to the renderer.
 *
 * A host without a usable keychain (headless Linux, WSL, CI) gets the secret
 * held in memory for that launch and **nothing on disk**: a plaintext credential
 * leaks through every home-directory backup and sync, and a "key" stored next to
 * its ciphertext would only look like encryption. The price is one sign-in per
 * launch on those hosts — the server keeps a single `desktop_device` row, so
 * re-registering replaces it instead of piling up devices.
 *
 * The cipher is injected so this module stays free of Electron imports and can
 * be unit-tested outside a running app.
 */

export const DEVICE_CREDENTIAL_FILE = "desktop-device.json";
/** Owner-only: the file is a reusable credential. */
export const DEVICE_CREDENTIAL_MODE = 0o600;

export interface CredentialCipher {
  /**
   * False on hosts without a usable keychain (headless Linux, some CI) — and on
   * Linux specifically, false when safeStorage would silently fall back to its
   * hardcoded passphrase.
   */
  available(): Promise<boolean>;
  encrypt(plain: string): Promise<string>;
  decrypt(payload: string): Promise<string>;
}

interface StoredCredential {
  v: 1;
  /** Always true for files this build writes; v1 could also write plaintext. */
  encrypted: boolean;
  secret: string;
}

export interface LoadedCredential {
  secret: string;
  /** True when this call minted the secret (first boot, or after clear()). */
  created: boolean;
}

export class DeviceCredentialStore {
  // Assigned field-by-field: parameter properties are not supported by the
  // strip-only TypeScript loader the tests use.
  private readonly home: string;
  private readonly cipher: CredentialCipher;
  /**
   * Non-null only while this host has no keychain. It keeps renewal working for
   * the current launch and is deliberately lost on exit.
   */
  private inMemory: string | null = null;

  constructor(home: string, cipher: CredentialCipher) {
    this.home = home;
    this.cipher = cipher;
  }

  get path(): string {
    return join(this.home, DEVICE_CREDENTIAL_FILE);
  }

  /** Read the stored secret, or null when absent/unreadable/undecryptable. */
  async read(): Promise<string | null> {
    if (this.inMemory !== null) return this.inMemory;
    let raw: string;
    try {
      raw = await fs.readFile(this.path, "utf8");
    } catch {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as Partial<StoredCredential>;
      // A v1 plaintext file is not a credential this build accepts; migrate()
      // is the only path that may adopt one.
      if (parsed.encrypted !== true) return null;
      if (typeof parsed.secret !== "string" || parsed.secret.length === 0) return null;
      if (!(await this.cipher.available())) return null;
      const plain = await this.cipher.decrypt(parsed.secret);
      return plain.length > 0 ? plain : null;
    } catch {
      // Corrupt or written by another OS account: treat as absent, regenerate.
      return null;
    }
  }

  /**
   * Converge whatever an older build left behind into a form this host can keep
   * safely: re-encrypt a v1 plaintext file when a keychain exists, otherwise
   * adopt its secret for this launch and delete it.
   */
  async migrate(): Promise<void> {
    let raw: string;
    try {
      raw = await fs.readFile(this.path, "utf8");
    } catch {
      return;
    }
    let parsed: Partial<StoredCredential>;
    try {
      parsed = JSON.parse(raw) as Partial<StoredCredential>;
    } catch {
      return;
    }
    if (parsed.encrypted !== false) return;

    const secret =
      typeof parsed.secret === "string" && parsed.secret.length > 0 ? parsed.secret : null;
    if (!secret) {
      await this.clear();
      return;
    }

    if (await this.cipher.available()) {
      await this.write(secret);
      console.info("[desktop] re-encrypted the plaintext device credential");
      return;
    }

    await this.clear();
    this.inMemory = secret;
    console.warn(
      "[desktop] deleted the plaintext device credential — no OS keychain here, so this install is remembered for this launch only",
    );
  }

  async getOrCreate(): Promise<LoadedCredential> {
    const existing = await this.read();
    if (existing) return { secret: existing, created: false };
    // 32 random bytes → 43 base64url chars, well above the server's 32 minimum.
    const secret = randomBytes(32).toString("base64url");
    await this.write(secret);
    return { secret, created: true };
  }

  async write(secret: string): Promise<void> {
    if (!(await this.cipher.available())) {
      // No keychain: the secret never touches the disk. Whatever is still there
      // is either v1 plaintext, which must not survive, or ciphertext we cannot
      // read right now — kept, because a locked keychain comes back.
      this.inMemory = secret;
      await this.dropPlaintextFile();
      return;
    }

    const payload: StoredCredential = {
      v: 1,
      encrypted: true,
      secret: await this.cipher.encrypt(secret),
    };
    await fs.mkdir(this.home, { recursive: true });
    await fs.writeFile(this.path, `${JSON.stringify(payload, null, 2)}\n`, {
      mode: DEVICE_CREDENTIAL_MODE,
    });
    // writeFile's mode is filtered by umask; chmod makes 0600 deterministic.
    await fs.chmod(this.path, DEVICE_CREDENTIAL_MODE);
    // The file is the source of truth again.
    this.inMemory = null;
  }

  /** Delete a leftover file that is not ciphertext: v1 plaintext, or junk. */
  private async dropPlaintextFile(): Promise<void> {
    let raw: string;
    try {
      raw = await fs.readFile(this.path, "utf8");
    } catch {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as Partial<StoredCredential>;
      if (parsed.encrypted === true) return;
    } catch {
      // Unparseable: a v1 plaintext write that was cut short, never a credential.
    }
    await fs.rm(this.path, { force: true }).catch((err: unknown) => {
      console.warn(`[desktop] could not clear the stored device credential: ${String(err)}`);
    });
  }

  async clear(): Promise<void> {
    this.inMemory = null;
    await fs.rm(this.path, { force: true });
  }
}
