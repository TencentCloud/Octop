import { useCallback, useEffect, useMemo, useState } from "react";
import { App, Button, Modal, Typography } from "antd";
import { Download, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { knowledgeBasesApi } from "../../../api/modules/knowledgeBases";
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

export function KnowledgeCitationPreviewModal({
  citation,
  open,
  onClose,
}: {
  citation: KnowledgeCitation | null;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [mode, setMode] = useState<PreviewMode>("text");
  const [kind, setKind] = useState<DocKind | null>(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [filename, setFilename] = useState("");
  /** Set when rich blob fetch 404s — switch to extracted text. */
  const [richMissing, setRichMissing] = useState(false);

  const subtitle = useMemo(() => {
    if (!citation) return "";
    const dir = knowledgeCitationDirectory(citation.path);
    const parts = [citation.kbName, dir].filter(Boolean);
    return parts.join(" · ");
  }, [citation]);

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
    if (!open || !citation) return;
    if (!citation.kbId || !citation.docId) {
      message.error(t("chat.citationPreviewFailed"));
      onClose();
      return;
    }

    let cancelled = false;
    setText("");
    setFilename(citation.filename);
    setRichMissing(false);
    setKind(null);

    const richKind = getDocKind(citation.filename);
    if (
      richKind &&
      richKind !== "ppt" &&
      isRichPreviewFilename(citation.filename)
    ) {
      setKind(richKind);
      setMode("rich");
      setLoading(false);
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

  const fetchBlob = useCallback(
    async (
      onProgress?: (loaded: number, total: number) => void,
      signal?: AbortSignal,
    ) => {
      if (!citation) {
        throw new Error("missing citation");
      }
      try {
        return await knowledgeBasesApi.fetchDocumentFile(
          citation.kbId,
          citation.docId,
          "inline",
          onProgress,
          signal,
        );
      } catch (error) {
        if (isNotFoundApiError(error)) {
          setRichMissing(true);
        }
        throw error;
      }
    },
    [citation],
  );

  const downloadOriginal = async () => {
    if (!citation) return;
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
      message.error(
        apiErrorMessage(error, t("knowledgeBases.downloadOriginalFailed"), t),
      );
    }
  };

  const openInKnowledgeBase = () => {
    if (!citation) return;
    navigate(knowledgeCitationHref(citation));
    onClose();
  };

  return (
    <Modal
      open={open}
      title={
        <div className={styles.titleBlock}>
          <div className={styles.titleMain}>
            {filename || citation?.filename || t("chat.citationPreview")}
          </div>
          {subtitle ? (
            <Typography.Text type="secondary" className={styles.titleSub}>
              {subtitle}
            </Typography.Text>
          ) : null}
        </div>
      }
      onCancel={onClose}
      footer={
        <div className={styles.footer}>
          <Button
            icon={<Download size={14} />}
            onClick={() => void downloadOriginal()}
          >
            {t("knowledgeBases.downloadOriginal")}
          </Button>
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
      }
      width={isRich ? "min(1200px, 92vw)" : 720}
      centered
      destroyOnHidden
      wrapClassName={styles.wrap}
      classNames={{ content: styles.content }}
      style={{ maxHeight: "calc(100vh - 48px)" }}
      styles={{
        body: {
          height: "78vh",
          flex: "0 1 auto",
          minHeight: 0,
          padding: 12,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        },
      }}
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
            onDownload={() => void downloadOriginal()}
          />
        </div>
      ) : mode === "markdown" ? (
        <div className={styles.textBody}>
          <Markdown content={stripFrontmatter(text)} />
        </div>
      ) : (
        <div className={styles.textBody}>
          <pre className={styles.pre}>{text}</pre>
        </div>
      )}
    </Modal>
  );
}
