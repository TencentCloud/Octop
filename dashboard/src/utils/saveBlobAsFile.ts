import { shareDownloadLink } from "./downloadLink";
import { isInAppBrowser } from "./inAppBrowser";

function clickDownloadAnchor(blob: Blob, filename: string): void {
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = filename || "download";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objUrl), 100);
}

/**
 * Persist a blob as a user download.
 *
 * Both Chromium (browser) and the Electron shell honour ``<a download>`` — the
 * shell's default download lands in the OS Downloads folder — so there is no
 * desktop-specific branch. In-app browsers (WeChat, …) refuse ``blob:``
 * downloads, so they get a short-lived link to open in the system browser.
 */
export async function saveBlobAsFile(
  blob: Blob,
  filename: string,
): Promise<void> {
  const name = filename.trim() || "download";
  if (isInAppBrowser()) {
    await shareDownloadLink(blob, name);
    return;
  }
  clickDownloadAnchor(blob, name);
}
