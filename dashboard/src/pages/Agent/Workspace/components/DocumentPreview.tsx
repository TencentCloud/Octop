/**
 * DocumentPreview — workspace wrapper around ``DocumentPreviewCore``.
 *
 * Bytes are fetched through the authenticated ``requestBlob`` helper.
 */

import { useCallback } from "react";
import DocumentPreviewCore from "../../../../components/DocumentPreviewCore";
import { requestBlob } from "../../../../api/request";
import { withFromWorkspace } from "../../../../utils/fromWorkspace";
import type { DocKind } from "../utils/docKind";
import styles from "../index.module.less";

interface DocumentPreviewProps {
  agentId: string;
  path: string;
  kind: DocKind;
  /** Workspace UI paths use true; chat/tool paths use false. */
  fromWorkspace?: boolean;
}

function documentDownloadUrl(
  agentId: string,
  path: string,
  fromWorkspace: boolean,
): string {
  const url = `/agents/${encodeURIComponent(
    agentId,
  )}/workspace/download?path=${encodeURIComponent(path)}`;
  return fromWorkspace ? withFromWorkspace(url) : `${url}&from_workspace=false`;
}

export default function DocumentPreview({
  agentId,
  path,
  kind,
  fromWorkspace = true,
}: DocumentPreviewProps) {
  const apiPath = documentDownloadUrl(agentId, path, fromWorkspace);
  const filename = path.split("/").filter(Boolean).pop() || path;

  const fetchBlob = useCallback(() => requestBlob(apiPath), [apiPath]);

  const onDownload = useCallback(async () => {
    try {
      const blob = await requestBlob(apiPath);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Download errors surface via the network layer.
    }
  }, [apiPath, filename]);

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
