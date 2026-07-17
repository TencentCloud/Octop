import { useCallback, useState } from "react";
import { message as antMessage } from "antd";
import { ArrowDownToLine, Eye, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { downloadAuthFile } from "../../../components/AuthFileDownloadLink";
import {
  isDataUrl,
  needsAuthBlobFetch,
  workspacePathFromAccessUrl,
} from "../../../utils/toolMediaBlocks";
import { getDocKind } from "../../Agent/Workspace/utils/docKind";
import { getMediaKind } from "../../Agent/Workspace/utils/mediaKind";
import { isProbablyText } from "../../Agent/Workspace/utils/fileKind";
import ChatFileModal from "./ChatFileModal";
import styles from "../index.module.less";

/** Files the browser can render inline (vs. pure binary blobs). */
function isPreviewable(name: string): boolean {
  return (
    isProbablyText(name) ||
    getMediaKind(name) !== null ||
    getDocKind(name) !== null
  );
}

/** Authenticated download card for chat / tool-result non-image files. */
export function MessageFileCard({
  url,
  filename,
  agentId,
  workspacePath,
}: {
  url: string;
  filename?: string;
  agentId?: string | null;
  workspacePath?: string;
}) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const needsAuth = needsAuthBlobFetch(url) || isDataUrl(url);
  const label = filename || url;

  const resolvedPath =
    workspacePath || workspacePathFromAccessUrl(url) || "";
  const previewable = Boolean(resolvedPath && agentId && isPreviewable(label));

  const handleDownload = useCallback(async () => {
    if (!needsAuth) {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || "download";
      a.target = "_blank";
      a.rel = "noreferrer";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      return;
    }
    setLoading(true);
    try {
      await downloadAuthFile(url, { filename });
    } catch {
      antMessage.error(t("chat.downloadFailed", "下载失败，请重试"));
    } finally {
      setLoading(false);
    }
  }, [url, filename, needsAuth, t]);

  const openPreview = useCallback(() => {
    if (previewable) setPreviewOpen(true);
  }, [previewable]);

  return (
    <div className={styles.messageFileCard}>
      <div
        className={styles.messageFileMeta}
        onClick={openPreview}
        role={previewable ? "button" : undefined}
        tabIndex={previewable ? 0 : undefined}
        onKeyDown={
          previewable
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  openPreview();
                }
              }
            : undefined
        }
        style={{ cursor: previewable ? "pointer" : "default" }}
      >
        <FileText size={14} className={styles.messageFileIcon} aria-hidden />
        <span className={styles.messageFileName} title={label}>
          {label}
        </span>
        {previewable && (
          <Eye
            size={14}
            className={styles.messageFilePreviewIcon}
            aria-hidden
          />
        )}
      </div>
      <button
        type="button"
        className={styles.messageFileDownloadBtn}
        onClick={(e) => {
          e.stopPropagation();
          void handleDownload();
        }}
        disabled={loading}
        title={t("common.download")}
        aria-label={t("common.download")}
      >
        <ArrowDownToLine size={16} strokeWidth={2} />
      </button>
      {previewOpen && resolvedPath && agentId && (
        <ChatFileModal
          agentId={agentId}
          open={previewOpen}
          initialPath={resolvedPath}
          filePaths={[resolvedPath]}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </div>
  );
}
