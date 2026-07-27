/**
 * FileViewer — single dispatch surface for rendering (and optionally editing)
 * a workspace file.
 *
 * It picks the right renderer by file type so both the workspace drawer and
 * the (future) chat file popups share one implementation:
 *
 *   - media (image / video / audio) -> ``MediaPreview``
 *   - documents (pdf / docx / xlsx) -> ``DocumentPreview``
 *   - markdown / html preview        -> ``FilePreview``
 *   - editable text in edit mode     -> ``CodeEditor`` (Monaco)
 *   - other text                     -> plain source (``<pre>``)
 *
 * Text content and edit state are owned by the parent so the toolbar save
 * button (in the drawer) stays in control; the viewer itself stays stateless
 * about persistence.
 */

import { useTranslation } from "react-i18next";
import { Spin } from "antd";
import FilePreview, { getPreviewKind } from "./FilePreview";
import MediaPreview from "./MediaPreview";
import CodeEditor from "./CodeEditor";
import DocumentPreview from "./DocumentPreview";
import { getMediaKind } from "../utils/mediaKind";
import { getDocKind } from "../utils/docKind";
import { isProbablyText } from "../utils/fileKind";
import styles from "../index.module.less";

interface FileViewerProps {
  agentId: string;
  path: string;
  /** Whether leading-slash paths come from the workspace UI. */
  fromWorkspace?: boolean;
  /** When true, text files render with the Monaco editor. */
  editMode: boolean;
  /** Current text content (for text/preview modes). */
  value: string;
  onChange: (value: string) => void;
  /** True while the parent is still fetching text content. */
  fileLoading?: boolean;
  /** Show rendered preview (markdown/code) vs raw source for text files. */
  previewMode?: boolean;
  /** Bump to reload media/document previews without unmounting. */
  refreshToken?: number;
}

export default function FileViewer({
  agentId,
  path,
  fromWorkspace = true,
  editMode,
  value,
  onChange,
  fileLoading = false,
  previewMode = true,
  refreshToken = 0,
}: FileViewerProps) {
  const { t } = useTranslation();

  const mediaKind = getMediaKind(path);
  const docKind = getDocKind(path);
  const previewKind = getPreviewKind(path);
  const showEditButton = isProbablyText(path);

  if (mediaKind) {
    return (
      <MediaPreview
        agentId={agentId}
        path={path}
        kind={mediaKind}
        refreshToken={refreshToken}
      />
    );
  }

  if (docKind) {
    return (
      <DocumentPreview
        key={`${path}:${refreshToken}`}
        agentId={agentId}
        path={path}
        kind={docKind}
        fromWorkspace={fromWorkspace}
      />
    );
  }

  if (fileLoading) {
    return (
      <div className={styles.viewerLoading}>
        <Spin />
      </div>
    );
  }

  if (!showEditButton) {
    return (
      <div className={styles.viewerEmpty}>
        <p style={{ color: "var(--fn-text-tertiary)", margin: 0 }}>
          {t("workspace.binaryHint", "该文件可能是二进制内容，请使用下载获取")}
        </p>
      </div>
    );
  }

  if (editMode) {
    return <CodeEditor path={path} value={value} onChange={onChange} />;
  }

  if (value === "") {
    return (
      <div className={styles.viewerEmpty}>
        <p style={{ color: "var(--fn-text-tertiary)", margin: 0 }}>
          {t("workspace.emptyFile", "文件为空")}
        </p>
      </div>
    );
  }

  if (previewKind && previewMode) {
    return <FilePreview kind={previewKind} content={value} />;
  }

  return <pre className={styles.viewerPre}>{value}</pre>;
}
