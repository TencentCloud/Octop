/**
 * Copy text to the clipboard, including plain HTTP (non-secure) pages.
 *
 * `navigator.clipboard` requires a secure context (https or localhost).
 * `copy-to-clipboard` falls back to execCommand so copy still works on
 * http:// admin hosts.
 *
 * @returns true when the text was copied, false otherwise.
 */
import copy from "copy-to-clipboard";

export async function copyText(text: string): Promise<boolean> {
  if (text === "") return false;
  try {
    return copy(text);
  } catch {
    return false;
  }
}
