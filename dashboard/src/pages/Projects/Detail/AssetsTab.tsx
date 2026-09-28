import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Spin, Typography } from "antd";
import {
  Download,
  ExternalLink,
  FileText,
  Folder,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  knowledgeBasesApi,
  type KnowledgeBase,
  type KnowledgeDocument,
} from "../../../api/modules/knowledgeBases";
import DocumentPreviewCore from "../../../components/DocumentPreviewCore";
import type { DocKind } from "../../../utils/docKind";
import { EmptyState } from "../../../components/EmptyState";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { getDocKind } from "../../../utils/docKind";
import {
  canPreviewKnowledgeDocument,
  isEditableKnowledgeDocument,
  isKnowledgeMarkdownDocument,
} from "../../../utils/knowledgeDocPreview";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./AssetsTab.module.less";

const { Text } = Typography;

/**
 * Assets tab — the project's knowledge base (PLAN §19.3 / §8 / 批次七 门三).
 *
 * There is deliberately **no asset model**: `projects.kb_id` is the whole data
 * source, and this component reads it through the existing knowledge-base API
 * wrapper. Nothing here invents a table, a column, or an "asset type".
 *
 * A `NULL` `kb_id` (feature off, or the KB could not be created) is an explicit
 * **non-error surface**: the tab renders the empty state with a way to bind one.
 * It must not raise, must not surface a failure, and must not be counted as an
 * acceptance failure anywhere.
 *
 * 批次七（门三）：**只读**浏览 —— 文件树/列表是这里的**紧凑自写版**，API 与预览器
 * 都复用既有的（`knowledgeBasesApi` + `DocumentPreviewCore`）；顶层知识库页
 * （3458 行单体）**未改动**。零写面：不做上传 / 建文件夹 / 重命名 / 删除。
 */
interface AssetsTabProps {
  /**
   * `projects.kb_id`. `null` means no knowledge base is bound — a supported
   * state, not a failure.
   */
  kbId: string | null;
}

/** 展示用路径（`path` 缺失时退回 `filename`）。 */
function docPath(doc: KnowledgeDocument): string {
  return doc.path ?? doc.filename;
}

/** 展示用名字（取路径末段）。 */
function docName(doc: KnowledgeDocument): string {
  const parts = docPath(doc)
    .split("/")
    .filter((part) => part.length > 0);
  return parts[parts.length - 1] ?? doc.filename;
}

/**
 * 「扁平 → 树」：后端 `prefix` 只返回**该目录的直接子项**（已核实路由描述），
 * 故这里把当前层级的扁平数组整理成「面包屑 + 目录 + 文件」（≤50 行、无新依赖）。
 */
function levelRows(entries: KnowledgeDocument[], prefix: string) {
  const collator = (a: KnowledgeDocument, b: KnowledgeDocument) =>
    docPath(a).localeCompare(docPath(b));
  const dirs = entries.filter((doc) => doc.is_dir).sort(collator);
  const files = entries.filter((doc) => !doc.is_dir).sort(collator);
  return {
    segments: prefix.split("/").filter((part) => part.length > 0),
    dirs,
    files,
  };
}

/** 图片类扩展名（顶层页无图片预览 ⇒ 本批按 lead 裁定用**既有取原文件通道**直接渲染）。 */
const IMAGE_EXTS = new Set([
  "jpg",
  "jpeg",
  "png",
  "webp",
  "gif",
  "bmp",
  "svg",
  "avif",
]);

function fileExt(path: string): string {
  const dot = path.lastIndexOf(".");
  return dot >= 0 ? path.slice(dot + 1).toLowerCase() : "";
}

/**
 * 预览通道（**对齐顶层知识库页对同一份数据的行为**——`L21` 的行为版）：
 * `rich` = `DocumentPreviewCore`（pdf/word/excel/pptx/ppt）·
 * `image` = 取原文件直接渲染 · `text` = 既有文本通道（UTF-8 或抽取文本）·
 * `unsupported` = **真正的未识别类型**才回退（回退节点保留）。
 */
type PreviewMode = "rich" | "image" | "text" | "unsupported";

function previewMode(doc: KnowledgeDocument): PreviewMode {
  const path = docPath(doc);
  if (getDocKind(path)) return "rich";
  if (IMAGE_EXTS.has(fileExt(path))) return "image";
  if (
    isKnowledgeMarkdownDocument(doc) ||
    isEditableKnowledgeDocument(doc) ||
    canPreviewKnowledgeDocument(doc)
  ) {
    return "text";
  }
  return "unsupported";
}

/**
 * 下载入口（**单一实现**）：四种预览模式共用同一个按钮组件，避免"某模式漏下载"。
 * 走既有 `…/documents/{id}/file?disposition=attachment`，不做整目录打包。
 */
function AssetDownloadButton({
  onDownload,
  testId,
}: {
  onDownload: () => void;
  testId: string;
}) {
  const { t } = useTranslation();
  return (
    <Button
      size="small"
      icon={<Download size={13} />}
      data-testid={testId}
      onClick={onDownload}
    >
      {t("knowledgeBases.downloadOriginal")}
    </Button>
  );
}

/** 文本通道：markdown/可编辑文档走 UTF-8（`/content`），其余可预览文本走抽取文本（`/preview`）。 */
function AssetTextPreview({
  kbId,
  doc,
  onDownload,
}: {
  kbId: string;
  doc: KnowledgeDocument;
  onDownload: () => void;
}) {
  const { t } = useTranslation();
  const raw =
    isKnowledgeMarkdownDocument(doc) || isEditableKnowledgeDocument(doc);
  const { data, loading } = useAsyncResource<{ text: string } | null>(
    null,
    () =>
      raw
        ? knowledgeBasesApi.getTextDocument(kbId, doc.id)
        : knowledgeBasesApi.previewDocument(kbId, doc.id),
    [kbId, doc.id, raw],
    { errorFallback: t("projects.loadFailed"), t, logLabel: "asset-text" },
  );

  // 未拿到内容前一律转圈：避免用「空态文案」冒充实内容（误导为「没有内容」）。
  if (loading || !data) {
    return (
      <div className={styles.centered} data-testid="asset-preview-text-loading">
        <Spin size="small" />
      </div>
    );
  }
  return (
    <div className={styles.textBlock}>
      <pre className={styles.text} data-testid="asset-preview-text">
        {data?.text?.trim() ? data.text : t("knowledgeBases.emptyDocuments")}
      </pre>
      <AssetDownloadButton
        onDownload={onDownload}
        testId="asset-download-text"
      />
    </div>
  );
}

/** 图片通道：既有取原文件端点（`inline`）→ object URL 直接渲染。 */
function AssetImagePreview({
  kbId,
  doc,
  onDownload,
}: {
  kbId: string;
  doc: KnowledgeDocument;
  onDownload: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    void (async () => {
      const blob = await knowledgeBasesApi.fetchDocumentFile(
        kbId,
        doc.id,
        "inline",
      );
      if (cancelled || typeof URL.createObjectURL !== "function") return;
      objectUrl = URL.createObjectURL(blob);
      setSrc(objectUrl);
    })();
    return () => {
      cancelled = true;
      // jsdom 无 revokeObjectURL（真实浏览器有）→ 守卫，避免 cleanup 抛错。
      if (objectUrl && typeof URL.revokeObjectURL === "function") {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [kbId, doc.id]);

  return (
    <div data-testid="asset-preview-image">
      {src ? (
        <img className={styles.image} src={src} alt={doc.filename} />
      ) : (
        <div className={styles.centered}>
          <Spin size="small" />
        </div>
      )}
      <AssetDownloadButton
        onDownload={onDownload}
        testId="asset-download-image"
      />
    </div>
  );
}

function AssetsTab({ kbId }: AssetsTabProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const timeZone = useServerTimezone();
  /** 当前浏览的目录前缀（空串 = 根）。 */
  const [prefix, setPrefix] = useState("");
  /** 选中待预览的文件。 */
  const [selected, setSelected] = useState<KnowledgeDocument | null>(null);

  // `enabled: false` is what keeps the empty branch honest: with no kb_id the
  // fetcher never runs, so the tab provably makes zero knowledge-base requests
  // instead of firing one and discarding the answer.
  const {
    data: kb,
    loading,
    refresh,
  } = useAsyncResource<KnowledgeBase | null>(
    null,
    () => knowledgeBasesApi.get(kbId as string),
    [kbId],
    {
      enabled: kbId !== null,
      errorFallback: t("projects.loadFailed"),
      t,
      logLabel: "project-assets",
    },
  );

  // 同一端点 + `prefix`（AC-B-1）：进入子目录不新增端点。
  const {
    data: documents,
    loading: docsLoading,
    refresh: refreshDocuments,
  } = useAsyncResource<KnowledgeDocument[]>(
    [],
    () => knowledgeBasesApi.listDocuments(kbId as string, prefix || undefined),
    [kbId, prefix],
    {
      enabled: kbId !== null,
      errorFallback: t("projects.loadFailed"),
      t,
      logLabel: "project-assets-documents",
    },
  );

  useEffect(() => {
    setPrefix("");
    setSelected(null);
  }, [kbId]);

  const { segments, dirs, files } = useMemo(
    () => levelRows(documents, prefix),
    [documents, prefix],
  );

  const openKnowledgeBases = () => navigate("/knowledge-bases");

  /** 下载：**既有** `…/documents/{id}/file` 端点（不新增下载面、不做整目录打包）。 */
  const download = useCallback(
    async (doc: KnowledgeDocument) => {
      const blob = await knowledgeBasesApi.fetchDocumentFile(
        kbId as string,
        doc.id,
        "attachment",
      );
      // jsdom 无 createObjectURL；真实浏览器里触发一次下载。
      if (typeof URL.createObjectURL !== "function") return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = docName(doc);
      link.click();
      URL.revokeObjectURL(url);
    },
    [kbId],
  );

  if (!kbId) {
    return (
      <div className={styles.section} data-testid="project-assets-empty">
        <EmptyState
          variant="empty"
          title={t("projects.assetEmpty")}
          actionLabel={t("projects.assetBind")}
          onAction={openKnowledgeBases}
        />
      </div>
    );
  }

  const mode: PreviewMode = selected ? previewMode(selected) : "unsupported";
  const kind = selected ? getDocKind(docPath(selected)) : null;

  return (
    <div className={styles.section} data-testid="project-assets">
      <div className={styles.sectionTitle}>
        {t("projects.assetTitle")}
        <span className={styles.headerActions}>
          <Button
            type="text"
            size="small"
            icon={<RefreshCw size={14} />}
            aria-label={t("common.refresh")}
            loading={loading || docsLoading}
            onClick={() => {
              void refresh();
              void refreshDocuments();
            }}
          />
          <Button
            type="link"
            size="small"
            icon={<ExternalLink size={14} />}
            onClick={() =>
              navigate(`/knowledge-bases?kb=${encodeURIComponent(kbId)}`)
            }
          >
            {t("projects.assetOpen")}
          </Button>
        </span>
      </div>
      {loading && !kb ? (
        <div className={styles.centered}>
          <Spin />
        </div>
      ) : kb ? (
        <div className={styles.meta}>
          <Text strong className={styles.name}>
            {kb.name}
          </Text>
          <Text type="secondary">
            {t("projects.assetDocCount", { count: kb.doc_count })}
          </Text>
          <Text type="secondary">
            {formatServerDateTime(kb.updated_at, timeZone)}
          </Text>
        </div>
      ) : null}

      {/* 面包屑：根 + 逐段（点击跳回该层）。 */}
      <div className={styles.crumbs}>
        <button
          type="button"
          className={styles.crumb}
          data-testid="asset-tree-root"
          onClick={() => {
            setPrefix("");
            setSelected(null);
          }}
        >
          {t("projects.assetTitle")}
        </button>
        {segments.map((segment, index) => {
          const target = segments.slice(0, index + 1).join("/");
          return (
            <span key={target} className={styles.crumbGroup}>
              <span className={styles.crumbSep}>/</span>
              <button
                type="button"
                className={styles.crumb}
                data-testid={`asset-tree-crumb-${target}`}
                onClick={() => {
                  setPrefix(target);
                  setSelected(null);
                }}
              >
                {segment}
              </button>
            </span>
          );
        })}
      </div>

      {docsLoading && documents.length === 0 ? (
        <div className={styles.centered}>
          <Spin size="small" />
        </div>
      ) : dirs.length === 0 && files.length === 0 ? (
        <Text type="secondary" data-testid="asset-tree-empty">
          {t("knowledgeBases.emptyDocuments")}
        </Text>
      ) : (
        <ul className={styles.tree} data-testid="asset-tree">
          {dirs.map((dir) => (
            <li key={docPath(dir)}>
              <button
                type="button"
                className={styles.row}
                data-testid={`asset-dir-${docPath(dir)}`}
                onClick={() => {
                  setPrefix(docPath(dir));
                  setSelected(null);
                }}
              >
                <Folder size={13} aria-hidden />
                <span className={styles.rowName}>{docName(dir)}</span>
              </button>
            </li>
          ))}
          {files.map((file) => (
            <li key={file.id}>
              <button
                type="button"
                className={styles.row}
                data-testid={`asset-file-${file.id}`}
                aria-pressed={selected?.id === file.id}
                onClick={() => setSelected(file)}
              >
                <FileText size={13} aria-hidden />
                <span className={styles.rowName}>{docName(file)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* 预览分派（对齐顶层知识库页的行为）：富文档 / 图片 / 文本 / 真·未识别回退。 */}
      {selected ? (
        <div className={styles.preview}>
          {mode === "rich" ? (
            <div data-testid="asset-preview">
              <DocumentPreviewCore
                kind={kind as DocKind}
                filename={selected.filename}
                fetchBlob={(onProgress, signal) =>
                  knowledgeBasesApi.fetchDocumentFile(
                    kbId,
                    selected.id,
                    "inline",
                    onProgress,
                    signal,
                  )
                }
                onDownload={() => void download(selected)}
              />
              {/* ★ `DocumentPreviewCore` 只在「不支持类型 / Excel 截断」两个分支才有下载
                  ⇒ 快乐路径（pdf/docx…）本组件补一个，保证**四种模式都有下载入口**。 */}
              <AssetDownloadButton
                onDownload={() => void download(selected)}
                testId="asset-download-rich"
              />
            </div>
          ) : mode === "image" ? (
            <AssetImagePreview
              kbId={kbId}
              doc={selected}
              onDownload={() => void download(selected)}
            />
          ) : mode === "text" ? (
            <AssetTextPreview
              kbId={kbId}
              doc={selected}
              onDownload={() => void download(selected)}
            />
          ) : (
            /* 真正的未识别类型 → 回退节点（不空白、不报错）：说明 + 下载。 */
            <div
              className={styles.unsupported}
              data-testid="asset-preview-unsupported"
            >
              <Text type="secondary">
                {t("knowledgeBases.previewUnsupported")}
              </Text>
              <AssetDownloadButton
                onDownload={() => void download(selected)}
                testId="asset-download-unsupported"
              />
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default AssetsTab;
