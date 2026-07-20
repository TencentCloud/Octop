import { useCallback, useState } from "react";
import { message as antMessage } from "antd";
import { Download, Eye, Paperclip } from "lucide-react";
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
import { useChatFilePreview } from "../ChatFilePreviewContext";
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
  const filePreview = useChatFilePreview();
  const [loading, setLoading] = useState(false);
  const needsAuth = needsAuthBlobFetch(url) || isDataUrl(url);
  const label = filename || url;

  const resolvedPath = workspacePath || workspacePathFromAccessUrl(url) || "";
  const previewable = Boolean(
    resolvedPath && agentId && isPreviewable(label) && filePreview,
  );

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
    if (previewable && resolvedPath && filePreview) {
      filePreview.openFilePreview(resolvedPath);
    }
  }, [previewable, resolvedPath, filePreview]);

  return (
    <div className={styles.messageFileCard}>
      <div className={styles.messageFileMeta}>
        <Paperclip
          size={16}
          strokeWidth={2}
          className={styles.messageFileIcon}
          aria-hidden
        />
        <span className={styles.messageFileName} title={label}>
          {label}
        </span>
      </div>
      {previewable && (
        <button
          type="button"
          className={styles.messageFileActionBtn}
          onClick={openPreview}
          title={t("common.preview")}
          aria-label={t("common.preview")}
        >
          <Eye size={15} strokeWidth={2} />
        </button>
      )}
      <button
        type="button"
        className={styles.messageFileActionBtn}
        onClick={(e) => {
          e.stopPropagation();
          void handleDownload();
        }}
        disabled={loading}
        title={t("common.download")}
        aria-label={t("common.download")}
      >
        <Download size={15} strokeWidth={2} />
      </button>
    </div>
  );
}
