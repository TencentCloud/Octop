/**
 * Browser WebAuthn helpers for MFA / passwordless passkeys.
 * Options and assertions use base64url strings as returned by py_webauthn JSON.
 */

import type { TFunction } from "i18next";

const BASE64URL_RE = /^[A-Za-z0-9_-]+$/;

export function isWebAuthnAvailable(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext === true &&
    typeof window.PublicKeyCredential !== "undefined" &&
    typeof navigator.credentials?.get === "function" &&
    typeof navigator.credentials?.create === "function"
  );
}

/**
 * Browsers reject IP literals as WebAuthn RP IDs ("This is an invalid domain").
 * Local HTTP dev must use the hostname ``localhost``, not ``127.0.0.1`` / ``::1``.
 */
export function isWebAuthnIpHost(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  if (host === "127.0.0.1" || host === "::1" || host === "[::1]") {
    return true;
  }
  // IPv4
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(host)) {
    return true;
  }
  // IPv6 (location.hostname is unbracketed)
  if (host.includes(":")) {
    return true;
  }
  return false;
}

/** Whether the browser supports Conditional UI (passkey autofill). */
export async function isConditionalMediationAvailable(): Promise<boolean> {
  if (!isWebAuthnAvailable() || isWebAuthnIpHost()) return false;
  const pk = window.PublicKeyCredential as
    | (typeof PublicKeyCredential & {
        isConditionalMediationAvailable?: () => Promise<boolean>;
      })
    | undefined;
  if (typeof pk?.isConditionalMediationAvailable !== "function") {
    return false;
  }
  try {
    return await pk.isConditionalMediationAvailable();
  } catch {
    return false;
  }
}

function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function base64urlToBuffer(value: string): ArrayBuffer {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const pad =
    normalized.length % 4 === 0 ? "" : "=".repeat(4 - (normalized.length % 4));
  const binary = atob(normalized + pad);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function decodeBufferField(value: unknown, field: string): ArrayBuffer {
  if (typeof value !== "string" || !value || !BASE64URL_RE.test(value)) {
    throw new Error(`Invalid WebAuthn ${field}`);
  }
  return base64urlToBuffer(value);
}

/** PublicKeyCredentialRequestOptions as JSON from the server. */
export type PublicKeyRequestOptionsJSON = {
  challenge: string;
  timeout?: number;
  rpId?: string;
  allowCredentials?: Array<{
    type: PublicKeyCredentialType;
    id: string;
    transports?: AuthenticatorTransport[];
  }>;
  userVerification?: UserVerificationRequirement;
  extensions?: AuthenticationExtensionsClientInputs;
};

/** PublicKeyCredentialCreationOptions as JSON from the server. */
export type PublicKeyCreationOptionsJSON = {
  challenge: string;
  rp: PublicKeyCredentialRpEntity;
  user: {
    id: string;
    name: string;
    displayName: string;
  };
  pubKeyCredParams: PublicKeyCredentialParameters[];
  timeout?: number;
  excludeCredentials?: Array<{
    type: PublicKeyCredentialType;
    id: string;
    transports?: AuthenticatorTransport[];
  }>;
  authenticatorSelection?: AuthenticatorSelectionCriteria;
  attestation?: AttestationConveyancePreference;
  extensions?: AuthenticationExtensionsClientInputs;
};

export type AuthenticationCredentialJSON = {
  id: string;
  rawId: string;
  type: PublicKeyCredentialType;
  authenticatorAttachment?: AuthenticatorAttachment | null;
  response: {
    clientDataJSON: string;
    authenticatorData: string;
    signature: string;
    userHandle: string | null;
  };
  clientExtensionResults: AuthenticationExtensionsClientOutputs;
};

export type RegistrationCredentialJSON = {
  id: string;
  rawId: string;
  type: PublicKeyCredentialType;
  authenticatorAttachment?: AuthenticatorAttachment | null;
  response: {
    clientDataJSON: string;
    attestationObject: string;
    transports?: AuthenticatorTransport[];
  };
  clientExtensionResults: AuthenticationExtensionsClientOutputs;
};

function toRequestOptions(
  options: PublicKeyRequestOptionsJSON,
): PublicKeyCredentialRequestOptions {
  const allow =
    options.allowCredentials && options.allowCredentials.length > 0
      ? options.allowCredentials.map((cred) => ({
          type: cred.type,
          id: decodeBufferField(cred.id, "allowCredentials.id"),
          transports: cred.transports,
        }))
      : undefined;
  return {
    challenge: decodeBufferField(options.challenge, "challenge"),
    timeout: options.timeout,
    rpId: options.rpId,
    // Omit empty allowCredentials — some authenticators treat [] poorly.
    ...(allow ? { allowCredentials: allow } : {}),
    userVerification: options.userVerification,
    extensions: options.extensions,
  };
}

/**
 * Map browser WebAuthn/DOMException messages to localized copy.
 * Returns ``null`` when the error is not a known browser WebAuthn failure
 * (caller should fall back to API / generic messaging).
 */
export function webauthnErrorMessage(
  error: unknown,
  t: TFunction,
): string | null {
  const name =
    error && typeof error === "object" && "name" in error
      ? String((error as { name?: string }).name || "")
      : "";
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "";
  if (
    name === "NotAllowedError" ||
    /timed out or was not allowed|not allowed/i.test(message)
  ) {
    return t("login.passkeyNotAllowed");
  }
  if (
    name === "AbortError" ||
    /WebAuthn cancelled|aborted|AbortError/i.test(message)
  ) {
    return t("login.passkeyCancelled");
  }
  if (name === "InvalidStateError") {
    return t("login.passkeyInvalidState");
  }
  if (
    name === "SecurityError" ||
    /invalid domain|secure context/i.test(message)
  ) {
    return t("apiErrors.WEBAUTHN_INVALID_DOMAIN");
  }
  if (/WebAuthn unavailable/i.test(message)) {
    return t("login.passkeyHttpsRequired");
  }
  return null;
}

function toCreationOptions(
  options: PublicKeyCreationOptionsJSON,
): PublicKeyCredentialCreationOptions {
  return {
    challenge: decodeBufferField(options.challenge, "challenge"),
    rp: options.rp,
    user: {
      id: decodeBufferField(options.user.id, "user.id"),
      name: options.user.name,
      displayName: options.user.displayName,
    },
    pubKeyCredParams: options.pubKeyCredParams,
    timeout: options.timeout,
    excludeCredentials: options.excludeCredentials?.map((cred) => ({
      type: cred.type,
      id: decodeBufferField(cred.id, "excludeCredentials.id"),
      transports: cred.transports,
    })),
    authenticatorSelection: options.authenticatorSelection,
    attestation: options.attestation,
    extensions: options.extensions,
  };
}

function assertionToJSON(
  credential: PublicKeyCredential,
): AuthenticationCredentialJSON {
  const response = credential.response as AuthenticatorAssertionResponse;
  const attachment = credential.authenticatorAttachment;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type as PublicKeyCredentialType,
    authenticatorAttachment:
      attachment === "platform" || attachment === "cross-platform"
        ? attachment
        : null,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle
        ? bufferToBase64url(response.userHandle)
        : null,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

function attestationToJSON(
  credential: PublicKeyCredential,
): RegistrationCredentialJSON {
  const response = credential.response as AuthenticatorAttestationResponse;
  const transports =
    typeof response.getTransports === "function"
      ? (response.getTransports() as AuthenticatorTransport[])
      : undefined;
  const attachment = credential.authenticatorAttachment;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type as PublicKeyCredentialType,
    authenticatorAttachment:
      attachment === "platform" || attachment === "cross-platform"
        ? attachment
        : null,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      transports,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

/** Run a WebAuthn assertion ceremony (login or MFA second factor). */
export async function webauthnGet(
  options: PublicKeyRequestOptionsJSON,
  signal?: AbortSignal,
): Promise<AuthenticationCredentialJSON> {
  if (!isWebAuthnAvailable()) {
    throw new Error("WebAuthn unavailable");
  }
  const credential = (await navigator.credentials.get({
    publicKey: toRequestOptions(options),
    signal,
  })) as PublicKeyCredential | null;
  if (!credential) {
    throw new Error("WebAuthn cancelled");
  }
  return assertionToJSON(credential);
}

/**
 * Conditional UI: stays pending until the user picks a passkey from autofill.
 * Callers should treat AbortError / NotAllowedError as silent cancellation.
 */
export async function webauthnGetConditional(
  options: PublicKeyRequestOptionsJSON,
  signal?: AbortSignal,
): Promise<AuthenticationCredentialJSON> {
  if (!isWebAuthnAvailable()) {
    throw new Error("WebAuthn unavailable");
  }
  // Conditional mediation needs a long timeout (challenge may wait minutes).
  const publicKey = toRequestOptions({
    ...options,
    timeout: Math.max(options.timeout ?? 0, 300_000),
  });
  const credential = (await navigator.credentials.get({
    publicKey,
    mediation: "conditional",
    signal,
  })) as PublicKeyCredential | null;
  if (!credential) {
    throw new Error("WebAuthn cancelled");
  }
  return assertionToJSON(credential);
}

export function isWebAuthnAbortError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const name = "name" in error ? String((error as { name?: string }).name) : "";
  if (name === "AbortError") return true;
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "";
  return /aborted|AbortError|WebAuthn cancelled/i.test(message);
}

/** Run a WebAuthn registration ceremony. */
export async function webauthnCreate(
  options: PublicKeyCreationOptionsJSON,
): Promise<RegistrationCredentialJSON> {
  if (!isWebAuthnAvailable()) {
    throw new Error("WebAuthn unavailable");
  }
  const credential = (await navigator.credentials.create({
    publicKey: toCreationOptions(options),
  })) as PublicKeyCredential | null;
  if (!credential) {
    throw new Error("WebAuthn cancelled");
  }
  return attestationToJSON(credential);
}
