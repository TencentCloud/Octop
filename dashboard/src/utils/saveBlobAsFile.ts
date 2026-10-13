import { message } from "@/utils/antdMessage";

import { requestUpload } from "../api/request";
import i18n from "../i18n";
import { isDesktopShell } from "./desktopChrome";

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
  clickDownloadAnchor(blob, name);
}
