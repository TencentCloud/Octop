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
import { saveBlobAsFile } from "../../../../utils/saveBlobAsFile";
import { withFromWorkspace } from "../../../../utils/fromWorkspace";
import { fetchOfficePdf } from "../../../../utils/officePreview";
import { canConvertOfficeToPdf, type DocKind } from "../utils/docKind";
import styles from "../index.module.less";

interface DocumentPreviewProps {
  agentId?: string;
  path: string;
  kind: DocKind;
  /** Workspace UI paths use true; chat/tool paths use false. */
  fromWorkspace?: boolean;
  fetchUrl?: string;
  /** Authorized Office → PDF endpoint; constructed from agentId when omitted. */
  officePreviewUrl?: string;
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

function documentOfficePreviewUrl(
  agentId: string,
  path: string,
  fromWorkspace: boolean,
): string {
  const url = `/agents/${encodeURIComponent(
    agentId,
  )}/workspace/office-preview?path=${encodeURIComponent(path)}`;
  return fromWorkspace ? withFromWorkspace(url) : `${url}&from_workspace=false`;
}

export default function DocumentPreview({
  agentId,
  path,
  kind,
  fromWorkspace = true,
  fetchUrl,
  officePreviewUrl,
}: DocumentPreviewProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const apiPath =
    fetchUrl || documentDownloadUrl(agentId ?? "", path, fromWorkspace);
  const filename = path.split("/").filter(Boolean).pop() || path;
  const pdfUrl =
    officePreviewUrl ||
    (agentId && canConvertOfficeToPdf(path)
      ? documentOfficePreviewUrl(agentId, path, fromWorkspace)
      : undefined);

  const fetchBlob = useCallback(
    (
      onProgress?: (loaded: number, total: number) => void,
      signal?: AbortSignal,
    ) => requestBlob(apiPath, { signal }, onProgress),
    [apiPath],
  );

  const fetchPdfPreview = useCallback(
    (
      onProgress?: (loaded: number, total: number) => void,
      signal?: AbortSignal,
    ) => {
      if (!pdfUrl) {
        return Promise.reject(new Error("office preview url missing"));
      }
      return fetchOfficePdf(pdfUrl, onProgress, signal);
    },
    [pdfUrl],
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
      <DocumentPreviewCore
        kind={kind}
        filename={filename}
        fetchBlob={fetchBlob}
        fetchPdfPreview={pdfUrl ? fetchPdfPreview : undefined}
        onDownload={onDownload}
      />
    </div>
  );
}
