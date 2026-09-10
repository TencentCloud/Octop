import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App, Button, Drawer, Tooltip, Typography } from "antd";
import {
  ArrowUpToLine,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
} from "lucide-react";
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
import {
  knowledgeCitationDirectory,
  knowledgeCitationHref,
} from "../../../utils/knowledgeCitationDisplay";
import {
  isEditableKnowledgeDocument,
  isKnowledgeMarkdownDocument,
  isRichPreviewFilename,
} from "../../../utils/knowledgeDocPreview";
import { stripFrontmatter } from "../../../utils/markdown";
import type { KnowledgeCitation } from "../../../utils/parseKnowledgeCitations";
import styles from "./KnowledgeCitationPreviewModal.module.less";

type PreviewMode = "rich" | "markdown" | "text";

const DOC_LIST_TTL_MS = 30_000;
const docListCache = new Map<
  string,
  { at: number; docs: KnowledgeDocument[] }
>();

function citationDrawerWidth(): number {
  if (typeof window === "undefined") return 880;
  return Math.min(880, window.innerWidth - 16);
}

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

export function KnowledgeCitationPreviewModal({
  citation,
  citations,
  open,
  onClose,
  onCitationChange,
}: {
  citation: KnowledgeCitation | null;
  /** Full strip list — enables prev/next when length > 1. */
  citations: KnowledgeCitation[];
  open: boolean;
  onClose: () => void;
  onCitationChange?: (next: KnowledgeCitation) => void;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const textBodyRef = useRef<HTMLDivElement | null>(null);

  const [mode, setMode] = useState<PreviewMode>("text");
  const [kind, setKind] = useState<DocKind | null>(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [filename, setFilename] = useState("");
  const [resolvedPath, setResolvedPath] = useState<string | undefined>();
  const [canDownload, setCanDownload] = useState(false);
  /** Set when rich blob fetch 404s — switch to extracted text. */
  const [richMissing, setRichMissing] = useState(false);

  const citationIndex = useMemo(() => {
    if (!citation) return -1;
    return citations.findIndex((row) => row.docId === citation.docId);
  }, [citation, citations]);
  const hasPrev = citationIndex > 0;
  const hasNext = citationIndex >= 0 && citationIndex < citations.length - 1;

  const titleFilename =
    filename || citation?.filename || t("chat.citationPreview");
  const titleKbName = citation?.kbName?.trim() || "";
  const titleFull = titleKbName
    ? `${titleFilename} · ${titleKbName}`
    : titleFilename;
  const subtitle = useMemo(() => {
    if (!citation) return "";
    const path = resolvedPath || citation.path;
    return knowledgeCitationDirectory(path);
  }, [citation, resolvedPath]);

  const isRich = mode === "rich" && kind != null && !richMissing;

  const goRelative = useCallback(
    (delta: number) => {
      if (!onCitationChange || citationIndex < 0) return;
      const next = citations[citationIndex + delta];
      if (next) onCitationChange(next);
    },
    [citationIndex, citations, onCitationChange],
  );

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
    if (!open || !citation) return;
    if (!citation.kbId || !citation.docId) {
      message.error(t("chat.citationPreviewFailed"));
      onClose();
      return;
    }

    let cancelled = false;
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
      // Optimistic until blob proves otherwise (or meta says no original).
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
      onClose();
    });

    return () => {
      cancelled = true;
    };
  }, [citation, loadTextPreview, message, onClose, open, t]);

  useEffect(() => {
    if (!open || !citation || !richMissing) return;
    setCanDownload(false);
    let cancelled = false;
    void loadTextPreview(citation).catch((error: unknown) => {
      if (cancelled) return;
      message.error(apiErrorMessage(error, t("chat.citationPreviewFailed"), t));
      onClose();
    });
    return () => {
      cancelled = true;
    };
  }, [citation, loadTextPreview, message, onClose, open, richMissing, t]);

  // Esc is handled by Drawer; also support ←/→ when multiple citations.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft" && hasPrev) {
        event.preventDefault();
        goRelative(-1);
      } else if (event.key === "ArrowRight" && hasNext) {
        event.preventDefault();
        goRelative(1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goRelative, hasNext, hasPrev, open]);

  const fetchBlob = useCallback(
    async (
      onProgress?: (loaded: number, total: number) => void,
      signal?: AbortSignal,
    ) => {
      if (!citation) {
        throw new Error("missing citation");
      }
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
    [citation],
  );

  const downloadOriginal = async () => {
    if (!citation || !canDownload) return;
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
  };

  const openInKnowledgeBase = () => {
    if (!citation) return;
    const hrefCitation =
      resolvedPath && resolvedPath !== citation.path
        ? { ...citation, path: resolvedPath }
        : citation;
    navigate(knowledgeCitationHref(hrefCitation));
    onClose();
  };

  const scrollMarkdownTop = () => {
    textBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <Drawer
      open={open}
      placement="right"
      title={
        <div className={styles.titleBlock}>
          <div className={styles.titleMain} title={titleFull}>
            <span className={styles.titleFilename}>{titleFilename}</span>
            {titleKbName ? (
              <span className={styles.titleKb}> · {titleKbName}</span>
            ) : null}
          </div>
          {subtitle ? (
            <Typography.Text type="secondary" className={styles.titleSub}>
              {subtitle}
            </Typography.Text>
          ) : null}
        </div>
      }
      onClose={onClose}
      destroyOnHidden
      width={citationDrawerWidth()}
      className={styles.drawer}
      styles={{
        body: {
          padding: 12,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
        footer: { padding: "12px 20px" },
      }}
      footer={
        <div className={styles.footer}>
          {citations.length > 1 ? (
            <div className={styles.navGroup}>
              <Button
                icon={<ChevronLeft size={14} />}
                disabled={!hasPrev}
                onClick={() => goRelative(-1)}
                aria-label={t("knowledgeBases.previewPrev")}
              />
              <span className={styles.navIndex}>
                {citationIndex + 1}/{citations.length}
              </span>
              <Button
                icon={<ChevronRight size={14} />}
                disabled={!hasNext}
                onClick={() => goRelative(1)}
                aria-label={t("knowledgeBases.previewNext")}
              />
            </div>
          ) : null}
          <div className={styles.footerActions}>
            {canDownload ? (
              <Button
                icon={<Download size={14} />}
                onClick={() => void downloadOriginal()}
              >
                {t("knowledgeBases.downloadOriginal")}
              </Button>
            ) : null}
            <Button
              icon={<ExternalLink size={14} />}
              onClick={openInKnowledgeBase}
            >
              {t("chat.citationViewInKnowledgeBase")}
            </Button>
            <Button type="primary" onClick={onClose}>
              {t("common.close")}
            </Button>
          </div>
        </div>
      }
    >
      {loading ? (
        <div className={styles.centered}>
          <DocumentPreviewLoading phase="file" />
        </div>
      ) : isRich && kind ? (
        <div className={styles.richBody}>
          <DocumentPreviewCore
            key={`${citation?.kbId}:${citation?.docId}`}
            kind={kind}
            filename={filename || citation?.filename || ""}
            fetchBlob={fetchBlob}
            onDownload={canDownload ? () => void downloadOriginal() : undefined}
          />
        </div>
      ) : mode === "markdown" ? (
        <div className={styles.mdWrap}>
          <div className={styles.mdToolbar}>
            <Tooltip title={t("chat.citationScrollTop")}>
              <Button
                type="text"
                size="small"
                icon={<ArrowUpToLine size={14} />}
                onClick={scrollMarkdownTop}
                aria-label={t("chat.citationScrollTop")}
              />
            </Tooltip>
          </div>
          <div ref={textBodyRef} className={styles.textBody}>
            <Markdown content={stripFrontmatter(text)} />
          </div>
        </div>
      ) : (
        <div ref={textBodyRef} className={styles.textBody}>
          <pre className={styles.pre}>{text}</pre>
        </div>
      )}
    </Drawer>
  );
}
