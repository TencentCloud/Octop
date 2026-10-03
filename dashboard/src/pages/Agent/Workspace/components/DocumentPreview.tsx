/**
 * DocumentPreview — workspace wrapper around ``DocumentPreviewCore``.
 *
 * Bytes are fetched through the authenticated ``requestBlob`` helper.
 */

import { useCallback } from "react";
import { App } from "antd";
import { useTranslation } from "react-i18next";
import DocumentPreviewCore from "../../../../components/DocumentPreviewCore";
import { requestBlob } from "../../../../api/request";
import { apiErrorMessage } from "../../../../utils/apiError";
import type { DocKind } from "../utils/docKind";
import styles from "../index.module.less";

interface DocumentPreviewProps {
  agentId: string;
  path: string;
  kind: DocKind;
}

function documentDownloadUrl(agentId: string, path: string): string {
  // SEC-2 durable fix: no from_workspace param — paths resolve
  // workspace-relative on the API.
  return `/agents/${encodeURIComponent(
    agentId,
  )}/workspace/download?path=${encodeURIComponent(path)}`;
}

export default function DocumentPreview({
  agentId,
  path,
  kind,
}: DocumentPreviewProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const apiPath = documentDownloadUrl(agentId, path);
  const filename = path.split("/").filter(Boolean).pop() || path;

  const fetchBlob = useCallback(
    (
      onProgress?: (loaded: number, total: number) => void,
      signal?: AbortSignal,
    ) => requestBlob(apiPath, { signal }, onProgress),
    [apiPath],
  );

  const onDownload = useCallback(async () => {
    try {
      const blob = await requestBlob(apiPath);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      message.error(apiErrorMessage(error, t("workspace.downloadFailed"), t));
    }
  }, [apiPath, filename, message, t]);

  return (
    <div className={styles.documentPreview}>
      <DocumentPreviewCore
        kind={kind}
        filename={filename}
        fetchBlob={fetchBlob}
        onDownload={onDownload}
      />
    </div>
  );
}
