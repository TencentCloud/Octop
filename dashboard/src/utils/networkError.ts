/**
 * Detect browser/network failures from ``fetch`` (offline, DNS, refused).
 * Does not treat HTTP 4xx/5xx ``Error`` messages from ``request()`` as offline.
 */
export function isNetworkFetchError(error: unknown): boolean {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return true;
  }
  const name =
    error instanceof Error
      ? error.name
      : error && typeof error === "object" && "name" in error
      ? String((error as { name: unknown }).name)
      : "";
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
      ? error
      : String(error ?? "");
  if (
    /failed to fetch|networkerror|network request failed|load failed|err_network|err_internet_disconnected|err_connection|econnrefused|enotfound/i.test(
      message,
    )
  ) {
    return true;
  }
  // Chromium / Safari: TypeError("Failed to fetch") / "Load failed"
  if (name === "TypeError" && /fetch|load failed|network/i.test(message)) {
    return true;
  }
  return false;
}
