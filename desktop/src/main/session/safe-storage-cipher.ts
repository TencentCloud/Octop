import { safeStorage } from "electron";

import type { CredentialCipher } from "./device-credential";

/**
 * Encrypt the device credential with the OS keychain (Keychain on macOS, DPAPI
 * on Windows, libsecret/kwallet on Linux) via Electron's `safeStorage`.
 *
 * When no keychain is available the credential is stored in the clear and the
 * shell logs a warning: on a headless Linux box there is nothing better to fall
 * back to, and refusing to work at all would reintroduce the sign-in wall.
 */
export function safeStorageCipher(): CredentialCipher {
  return {
    available(): boolean {
      try {
        return safeStorage.isEncryptionAvailable();
      } catch {
        return false;
      }
    },
    encrypt(plain: string): string {
      return safeStorage.encryptString(plain).toString("base64");
    },
    decrypt(payload: string): string {
      return safeStorage.decryptString(Buffer.from(payload, "base64"));
    },
  };
}

export function warnIfKeychainUnavailable(cipher: CredentialCipher): void {
  if (cipher.available()) return;
  console.warn(
    "[desktop] OS keychain unavailable — the device credential is stored unencrypted in the data root",
  );
}
