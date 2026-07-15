/**
 * Copy text to the clipboard with a legacy fallback for non-secure contexts.
 *
 * The async Clipboard API is only available in secure contexts (https or
 * localhost). When it is unavailable or rejects, we fall back to a temporary
 * textarea + execCommand so the copy still works on plain-http admin pages.
 *
 * @returns true when the text was copied, false otherwise.
 */
export async function copyText(text: string): Promise<boolean> {
  if (text === "") return false;

  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // fall through to the legacy path
    }
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.left = "0";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}
