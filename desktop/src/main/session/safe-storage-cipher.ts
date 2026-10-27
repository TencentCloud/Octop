import { safeStorage } from "electron";

import type { CredentialCipher } from "./device-credential";

/**
 * Encrypt the device credential with the OS keychain (Keychain on macOS, DPAPI
 * on Windows, libsecret/kwallet on Linux) via Electron's `safeStorage`.
 *
 * Uses the asynchronous API: Electron 45 deprecates the synchronous one and
 * removes it in 46, and the async variants also tolerate a keychain that is
 * temporarily unavailable instead of blocking the main process.
 *
 * Linux needs the extra backend check. The provider is picked from the desktop
 * environment, not by probing it: an unrecognised session (server, container,
 * WSL, CI) falls back to `basic_text`, where the key is a hardcoded passphrase.
 * `isAsyncEncryptionAvailable()` still reports true in that state, so trusting it
 * alone would store "encrypted" data that anyone can read.
 *
 * When no keychain is available the caller must not persist anything at all;
 * `available()` returning false is the only signal it needs, and
 * `DeviceCredentialStore` answers it by keeping the secret in memory.
 */
export function safeStorageCipher(): CredentialCipher {
  return {
    async available(): Promise<boolean> {
      try {
        if (!(await safeStorage.isAsyncEncryptionAvailable())) return false;
        return !(process.platform === "linux" && hasPlaintextBackend());
      } catch {
        return false;
      }
    },
    async encrypt(plain: string): Promise<string> {
      const encrypted = await safeStorage.encryptStringAsync(plain);
      return encrypted.toString("base64");
    },
    async decrypt(payload: string): Promise<string> {
      // `shouldReEncrypt` is ignored on purpose: the payload is a single secret
      // that is rewritten whenever the shell re-registers, so a stale key never
      // outlives the next registration.
      const { result } = await safeStorage.decryptStringAsync(
        Buffer.from(payload, "base64"),
      );
      return result;
    },
  };
}

/** Linux only: true when nothing but the hardcoded passphrase is behind safeStorage. */
function hasPlaintextBackend(): boolean {
  const backend = safeStorage.getSelectedStorageBackend();
  return backend === "basic_text" || backend === "unknown";
}

export async function warnIfKeychainUnavailable(
  cipher: CredentialCipher,
): Promise<void> {
  if (await cipher.available()) return;
  console.warn(
    "[desktop] no usable OS keychain — the device credential stays in memory and this install will need to sign in again after a restart",
  );
}
