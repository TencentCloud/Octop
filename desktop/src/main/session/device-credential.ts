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
 * The cipher is injected so this module stays free of Electron imports and can
 * be unit-tested outside a running app.
 */

export const DEVICE_CREDENTIAL_FILE = "desktop-device.json";
/** Owner-only: the file is a reusable credential. */
export const DEVICE_CREDENTIAL_MODE = 0o600;

export interface CredentialCipher {
  /** False on hosts without a usable keychain (headless Linux, some CI). */
  available(): boolean;
  encrypt(plain: string): string;
  decrypt(payload: string): string;
}

interface StoredCredential {
  v: 1;
  /** Whether `secret` is ciphertext; false means the keychain was unavailable. */
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

  constructor(home: string, cipher: CredentialCipher) {
    this.home = home;
    this.cipher = cipher;
  }

  get path(): string {
    return join(this.home, DEVICE_CREDENTIAL_FILE);
  }

  /** Read the stored secret, or null when absent/unreadable/undecryptable. */
  async read(): Promise<string | null> {
    let raw: string;
    try {
      raw = await fs.readFile(this.path, "utf8");
    } catch {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as Partial<StoredCredential>;
      if (typeof parsed.secret !== "string" || parsed.secret.length === 0) return null;
      if (!parsed.encrypted) return parsed.secret;
      if (!this.cipher.available()) return null;
      const plain = this.cipher.decrypt(parsed.secret);
      return plain.length > 0 ? plain : null;
    } catch {
      // Corrupt or written by another OS account: treat as absent, regenerate.
      return null;
    }
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
    const encrypted = this.cipher.available();
    const payload: StoredCredential = {
      v: 1,
      encrypted,
      secret: encrypted ? this.cipher.encrypt(secret) : secret,
    };
    await fs.mkdir(this.home, { recursive: true });
    await fs.writeFile(this.path, `${JSON.stringify(payload, null, 2)}\n`, {
      mode: DEVICE_CREDENTIAL_MODE,
    });
    // writeFile's mode is filtered by umask; chmod makes 0600 deterministic.
    await fs.chmod(this.path, DEVICE_CREDENTIAL_MODE);
  }

  async clear(): Promise<void> {
    await fs.rm(this.path, { force: true });
  }
}
