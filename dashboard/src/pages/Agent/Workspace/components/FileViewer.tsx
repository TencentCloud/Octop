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

import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import FilePreview, { getPreviewKind } from "./FilePreview";
import DocumentPreviewLoading from "../../../../components/DocumentPreviewLoading";

// ★ 三路预览改**懒加载**（批次十四 `T-B-LAZY`）：此前是**静态全量分发器** ——
//   模块加载期就把三种预览（其中 `DocumentPreview → DocumentPreviewCore → react-pdf`）
//   全部拉进依赖图 ⇒ 即便只想看一张图片，也会在加载期要求 pdfjs 的全部全局
//   （实测：`ReferenceError: DOMMatrix is not defined`）。
//   ★ 改后**该边不再存在于模块加载期**；fallback 沿用既有 `DocumentPreviewLoading`，
//   **不新增 spinner**。
const MediaPreview = lazy(() => import("./MediaPreview"));
const CodeEditor = lazy(() => import("./CodeEditor"));
const DocumentPreview = lazy(() => import("./DocumentPreview"));
import { getMediaKind } from "../utils/mediaKind";
import {
  getDocKind,
  getEditableDocLanguage,
  isEditableDoc,
} from "../utils/docKind";
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
  const editableDoc = isEditableDoc(path);
  const showEditButton = isProbablyText(path) || editableDoc;
  const editingDoc = editMode && editableDoc;

  if (mediaKind) {
    return (
      <Suspense fallback={<DocumentPreviewLoading phase="file" />}>
        <MediaPreview
          agentId={agentId}
          path={path}
          kind={mediaKind}
          refreshToken={refreshToken}
          fromWorkspace={fromWorkspace}
        />
      </Suspense>
    );
  }

  if (docKind && !editingDoc) {
    return (
      <Suspense fallback={<DocumentPreviewLoading phase="file" />}>
        <DocumentPreview
          key={`${path}:${refreshToken}`}
          agentId={agentId}
          path={path}
          kind={docKind}
          fromWorkspace={fromWorkspace}
        />
      </Suspense>
    );
  }

  if (fileLoading) {
    return <DocumentPreviewLoading phase="file" />;
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
    return (
      <Suspense fallback={<DocumentPreviewLoading phase="file" />}>
        <CodeEditor
          path={path}
          value={value}
          onChange={onChange}
          language={
            editableDoc ? getEditableDocLanguage(path) ?? "markdown" : undefined
          }
        />
      </Suspense>
    );
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
