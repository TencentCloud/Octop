/**
 * Model3DPreview — workspace wrapper around lazy-loaded ``Model3DPreviewCore``.
 *
 * Fetches model bytes through the authenticated ``requestBlob`` helper.
 */

import { Suspense, lazy, useCallback } from "react";
import { App } from "antd";
import { useTranslation } from "react-i18next";
import DocumentPreviewLoading from "../../../../components/DocumentPreviewLoading";
import { requestBlob } from "../../../../api/request";
import { apiErrorMessage } from "../../../../utils/apiError";
import { saveBlobAsFile } from "../../../../utils/saveBlobAsFile";
import { withFromWorkspace } from "../../../../utils/fromWorkspace";
import type { Model3DKind } from "../utils/modelKind";
import styles from "../index.module.less";

const Model3DPreviewCore = lazy(
  () => import("../../../../components/Model3DPreviewCore"),
);

interface Model3DPreviewProps {
  agentId?: string;
  path: string;
  kind: Model3DKind;
  /** Workspace UI paths use true; chat/tool paths use false. */
  fromWorkspace?: boolean;
  fetchUrl?: string;
}

function modelDownloadUrl(
  agentId: string,
  path: string,
  fromWorkspace: boolean,
): string {
  const url = `/agents/${encodeURIComponent(
    agentId,
  )}/workspace/download?path=${encodeURIComponent(path)}`;
  return fromWorkspace ? withFromWorkspace(url) : `${url}&from_workspace=false`;
}

export default function Model3DPreview({
  agentId,
  path,
  kind,
  fromWorkspace = true,
  fetchUrl,
}: Model3DPreviewProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const apiPath =
    fetchUrl || modelDownloadUrl(agentId ?? "", path, fromWorkspace);
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
      await saveBlobAsFile(blob, filename);
    } catch (error) {
      message.error(apiErrorMessage(error, t("workspace.downloadFailed"), t));
    }
  }, [apiPath, filename, message, t]);

  return (
    <div className={styles.documentPreview}>
      <Suspense fallback={<DocumentPreviewLoading phase="file" />}>
        <Model3DPreviewCore
          kind={kind}
          filename={filename}
          fetchBlob={fetchBlob}
          onDownload={onDownload}
        />
      </Suspense>
    </div>
  );
}
