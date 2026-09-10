import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { App, Tooltip } from "antd";
import { ArrowDownToLine, ArrowUpToLine, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  knowledgeBasesApi,
  type KnowledgeDocument,
} from "../../../api/modules/knowledgeBases";
import DocumentPreviewCore from "../../../components/DocumentPreviewCore";
import DocumentPreviewLoading from "../../../components/DocumentPreviewLoading";
import Markdown from "../../../components/Markdown";
import { apiErrorMessage, isNotFoundApiError } from "../../../utils/apiError";
import { getDocKind, type DocKind } from "../../../utils/docKind";
import { knowledgeCitationHref } from "../../../utils/knowledgeCitationDisplay";
import {
  isEditableKnowledgeDocument,
  isKnowledgeMarkdownDocument,
  isRichPreviewFilename,
} from "../../../utils/knowledgeDocPreview";
import { stripFrontmatter } from "../../../utils/markdown";
import type { KnowledgeCitation } from "../../../utils/parseKnowledgeCitations";
import chatStyles from "../index.module.less";
import styles from "./KnowledgeCitationPanelContent.module.less";

type PreviewMode = "rich" | "markdown" | "text";

const DOC_LIST_TTL_MS = 30_000;
const docListCache = new Map<
  string,
  { at: number; docs: KnowledgeDocument[] }
>();

async function resolveCitationDocument(
  kbId: string,
  docId: string,
): Promise<KnowledgeDocument | null> {
  const now = Date.now();
  const cached = docListCache.get(kbId);
  let docs =
    cached && now - cached.at <= DOC_LIST_TTL_MS ? cached.docs : undefined;
  if (!docs) {
    docs = await knowledgeBasesApi.listDocuments(kbId);
    docListCache.set(kbId, { at: now, docs });
  }
  return docs.find((row) => row.id === docId && !row.is_dir) ?? null;
}

interface KnowledgeCitationPanelContentProps {
  citation: KnowledgeCitation;
  /** Lift toolbar actions into the shared dock shell (active tab only). */
  onActionsChange?: (actions: ReactNode | null) => void;
}

/**
 * Knowledge citation preview body for a chat dock tab (same shell as workspace
 * file tabs opened from “编辑了 N 个文件”).
 */
export default function KnowledgeCitationPanelContent({
  citation,
  onActionsChange,
}: KnowledgeCitationPanelContentProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const textBodyRef = useRef<HTMLDivElement | null>(null);

  const [mode, setMode] = useState<PreviewMode>("text");
  const [kind, setKind] = useState<DocKind | null>(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [filename, setFilename] = useState(citation.filename);
  const [resolvedPath, setResolvedPath] = useState<string | undefined>(
    citation.path,
  );
  const [canDownload, setCanDownload] = useState(false);
  const [richMissing, setRichMissing] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);

  const isRich = mode === "rich" && kind != null && !richMissing;

  const loadTextPreview = useCallback(
    async (c: KnowledgeCitation) => {
      setLoading(true);
      try {
        const asMarkdown = isKnowledgeMarkdownDocument({
          filename: c.filename,
        });
        const editable = isEditableKnowledgeDocument({ filename: c.filename });
        if (asMarkdown || editable) {
          const payload = await knowledgeBasesApi.getTextDocument(
            c.kbId,
            c.docId,
          );
          setFilename(payload.filename || c.filename);
          setText(
            payload.text.trim()
              ? payload.text
              : t("knowledgeBases.previewEmpty"),
          );
          setMode(asMarkdown ? "markdown" : "text");
          return;
        }
        const preview = await knowledgeBasesApi.previewDocument(
          c.kbId,
          c.docId,
        );
        setFilename(preview.filename || c.filename);
        setText(
          preview.text.trim() ? preview.text : t("knowledgeBases.previewEmpty"),
        );
        setMode("text");
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (!citation.kbId || !citation.docId) {
      message.error(t("chat.citationPreviewFailed"));
      setLoadFailed(true);
      return;
    }

    let cancelled = false;
    setLoadFailed(false);
    setText("");
    setFilename(citation.filename);
    setResolvedPath(citation.path);
    setRichMissing(false);
    setKind(null);
    setCanDownload(false);
    textBodyRef.current?.scrollTo({ top: 0 });

    const hydrateMeta = async () => {
      try {
        const doc = await resolveCitationDocument(
          citation.kbId,
          citation.docId,
        );
        if (cancelled || !doc) return;
        if (doc.path) setResolvedPath(doc.path);
        if (doc.filename) setFilename(doc.filename);
        const originalOk = doc.has_original !== false;
        setCanDownload(originalOk);
        if (!originalOk && isRichPreviewFilename(citation.filename)) {
          setRichMissing(true);
        }
      } catch {
        // Meta is best-effort; preview can still proceed.
      }
    };
    void hydrateMeta();

    const richKind = getDocKind(citation.filename);
    if (
      richKind &&
      richKind !== "ppt" &&
      isRichPreviewFilename(citation.filename)
    ) {
      setKind(richKind);
      setMode("rich");
      setLoading(false);
      setCanDownload(true);
      return () => {
        cancelled = true;
      };
    }

    setMode("text");
    setLoading(true);
    void loadTextPreview(citation).catch((error: unknown) => {
      if (cancelled) return;
      message.error(apiErrorMessage(error, t("chat.citationPreviewFailed"), t));
      setLoadFailed(true);
    });

    return () => {
      cancelled = true;
    };
  }, [citation, loadTextPreview, message, t]);

  useEffect(() => {
    if (!richMissing) return;
    setCanDownload(false);
    let cancelled = false;
    void loadTextPreview(citation).catch((error: unknown) => {
      if (cancelled) return;
      message.error(apiErrorMessage(error, t("chat.citationPreviewFailed"), t));
      setLoadFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [citation, loadTextPreview, message, richMissing, t]);

  const fetchBlob = useCallback(
    async (
      onProgress?: (loaded: number, total: number) => void,
      signal?: AbortSignal,
    ) => {
      try {
        const blob = await knowledgeBasesApi.fetchDocumentFile(
          citation.kbId,
          citation.docId,
          "inline",
          onProgress,
          signal,
        );
        setCanDownload(true);
        return blob;
      } catch (error) {
        if (isNotFoundApiError(error)) {
          setRichMissing(true);
          setCanDownload(false);
        }
        throw error;
      }
    },
    [citation.docId, citation.kbId],
  );

  const downloadOriginal = useCallback(async () => {
    if (!canDownload) return;
    try {
      const blob = await knowledgeBasesApi.fetchDocumentFile(
        citation.kbId,
        citation.docId,
        "attachment",
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || citation.filename || "download";
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      if (isNotFoundApiError(error)) {
        setCanDownload(false);
      }
      message.error(
        apiErrorMessage(error, t("knowledgeBases.downloadOriginalFailed"), t),
      );
    }
  }, [
    canDownload,
    citation.docId,
    citation.filename,
    citation.kbId,
    filename,
    message,
    t,
  ]);

  const openInKnowledgeBase = useCallback(() => {
    const hrefCitation =
      resolvedPath && resolvedPath !== citation.path
        ? { ...citation, path: resolvedPath }
        : citation;
    navigate(knowledgeCitationHref(hrefCitation));
  }, [citation, navigate, resolvedPath]);

  const scrollMarkdownTop = () => {
    textBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  useLayoutEffect(() => {
    if (!onActionsChange) return;
    const actions = (
      <>
        {canDownload ? (
          <Tooltip title={t("knowledgeBases.downloadOriginal")}>
            <button
              type="button"
              className={chatStyles.fileModalIconBtn}
              onClick={() => void downloadOriginal()}
              aria-label={t("knowledgeBases.downloadOriginal")}
            >
              <ArrowDownToLine size={16} strokeWidth={2} />
            </button>
          </Tooltip>
        ) : null}
        <Tooltip title={t("chat.citationViewInKnowledgeBase")}>
          <button
            type="button"
            className={chatStyles.fileModalIconBtn}
            onClick={openInKnowledgeBase}
            aria-label={t("chat.citationViewInKnowledgeBase")}
          >
            <ExternalLink size={16} strokeWidth={2} />
          </button>
        </Tooltip>
      </>
    );
    onActionsChange(actions);
    return () => onActionsChange(null);
  }, [canDownload, downloadOriginal, onActionsChange, openInKnowledgeBase, t]);

  if (loadFailed) {
    return (
      <div className={styles.centered}>
        <span className={styles.failedText}>
          {t("chat.citationPreviewFailed")}
        </span>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={styles.centered}>
        <DocumentPreviewLoading phase="file" />
      </div>
    );
  }

  if (isRich && kind) {
    return (
      <div className={styles.panel}>
        <div className={styles.richBody}>
          <DocumentPreviewCore
            key={`${citation.kbId}:${citation.docId}`}
            kind={kind}
            filename={filename || citation.filename || ""}
            fetchBlob={fetchBlob}
            onDownload={canDownload ? () => void downloadOriginal() : undefined}
          />
        </div>
      </div>
    );
  }

  if (mode === "markdown") {
    return (
      <div className={styles.panel}>
        <div className={styles.mdWrap}>
          <div className={styles.mdToolbar}>
            <Tooltip title={t("chat.citationScrollTop")}>
              <button
                type="button"
                className={chatStyles.fileModalIconBtn}
                onClick={scrollMarkdownTop}
                aria-label={t("chat.citationScrollTop")}
              >
                <ArrowUpToLine size={14} strokeWidth={2} />
              </button>
            </Tooltip>
          </div>
          <div ref={textBodyRef} className={styles.textBody}>
            <Markdown content={stripFrontmatter(text)} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div ref={textBodyRef} className={styles.textBody}>
        <pre className={styles.pre}>{text}</pre>
      </div>
    </div>
  );
}
