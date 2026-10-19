import { message } from "@/utils/antdMessage";

import { requestUpload } from "../api/request";
import i18n from "../i18n";
import { isDesktopShell } from "./desktopChrome";
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
 * Wails WebView ignores ``<a download>``. On the desktop shell we POST the
 * bytes to Octop (loopback-only) so they land in the host Downloads folder.
 * In-app browsers (WeChat, …) refuse ``blob:`` downloads, so they get a
 * short-lived link to open in the system browser instead.
 */
export async function saveBlobAsFile(
  blob: Blob,
  filename: string,
): Promise<void> {
  const name = filename.trim() || "download";
  if (isDesktopShell()) {
    const body = new FormData();
    body.append("file", blob, name);
    await requestUpload("/downloads/local", body);
    message.success(i18n.t("common.savedToDownloads", "已保存到下载文件夹"));
    return;
  }
  if (isInAppBrowser()) {
    await shareDownloadLink(blob, name);
    return;
  }
  clickDownloadAnchor(blob, name);
}
