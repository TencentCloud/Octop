/**
 * DocumentPreview — render rich documents (PDF / Word / Excel / PPTX) inside
 * the workspace viewer.
 *
 * PDFs use the browser native viewer via an ``<iframe>``. Word (``.docx``)
 * uses ``docx-preview``, Excel uses SheetJS HTML tables, and PPTX uses
 * ``@aiden0z/pptx-renderer``. Legacy ``.ppt`` only offers download. Heavy
 * libraries are dynamically imported so they ship only when opened.
 *
 * Bytes are fetched through the authenticated ``requestBlob`` helper.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Spin } from "antd";
import { ArrowDownToLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { requestBlob } from "../../../../api/request";
import type { DocKind } from "../utils/docKind";
import styles from "../index.module.less";

interface DocumentPreviewProps {
  agentId: string;
  path: string;
  kind: DocKind;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export default function DocumentPreview({
  agentId,
  path,
  kind,
}: DocumentPreviewProps) {
  const { t } = useTranslation();
  const [src, setSrc] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const objectUrlRef = useRef<string | undefined>(undefined);
  const pptxViewerRef = useRef<{ destroy: () => void } | null>(null);

  const handleDownload = useCallback(async () => {
    try {
      const blob = await requestBlob(
        `/agents/${encodeURIComponent(
          agentId,
        )}/workspace/download?path=${encodeURIComponent(path)}`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = path.split("/").filter(Boolean).pop() || "download";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Download errors surface via the network layer; nothing to recover here.
    }
  }, [agentId, path]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    setSrc("");
    pptxViewerRef.current?.destroy();
    pptxViewerRef.current = null;
    if (containerRef.current) containerRef.current.innerHTML = "";
    if (kind === "ppt") {
      setLoading(false);
      return;
    }

    const load = async () => {
      try {
        const blob = await requestBlob(
          `/agents/${encodeURIComponent(
            agentId,
          )}/workspace/download?path=${encodeURIComponent(path)}`,
        );
        if (cancelled) return;

        if (kind === "pdf") {
          // The download endpoint returns ``application/octet-stream``; coerce
          // the blob to ``application/pdf`` so the iframe viewer renders it
          // reliably across browsers instead of offering a download.
          const pdfBlob =
            blob.type === "application/pdf"
              ? blob
              : new Blob([blob], { type: "application/pdf" });
          const objUrl = URL.createObjectURL(pdfBlob);
          objectUrlRef.current = objUrl;
          setSrc(objUrl);
          setLoading(false);
          return;
        }

        const buf = await blob.arrayBuffer();
        if (cancelled) return;

        if (kind === "word") {
          const { renderAsync } = await import("docx-preview");
          if (containerRef.current && !cancelled) {
            await renderAsync(buf, containerRef.current, undefined, {
              className: "docx-doc",
              inWrapper: true,
              breakPages: true,
              ignoreWidth: false,
              ignoreHeight: false,
            });
          }
        } else if (kind === "excel") {
          const xlsx = await import("xlsx");
          const wb = xlsx.read(buf, { type: "array" });
          if (containerRef.current && !cancelled) {
            containerRef.current.innerHTML = wb.SheetNames.map((name) => {
              const html = xlsx.utils.sheet_to_html(wb.Sheets[name]);
              return (
                `<div class="${styles.xlsxSheet}">` +
                `<div class="${styles.xlsxSheetTitle}">${escapeHtml(
                  name,
                )}</div>` +
                html +
                "</div>"
              );
            }).join("");
          }
        } else if (kind === "pptx") {
          const { PptxViewer, RECOMMENDED_ZIP_LIMITS } = await import(
            "@aiden0z/pptx-renderer"
          );
          if (containerRef.current && !cancelled) {
            const viewer = await PptxViewer.open(buf, containerRef.current, {
              zipLimits: RECOMMENDED_ZIP_LIMITS,
              lazySlides: true,
              lazyMedia: true,
              listOptions: {
                windowed: true,
                initialSlides: 4,
                batchSize: 4,
              },
            });
            if (cancelled) viewer.destroy();
            else pptxViewerRef.current = viewer;
          }
        }
        if (!cancelled) setLoading(false);
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = undefined;
      }
      pptxViewerRef.current?.destroy();
      pptxViewerRef.current = null;
    };
  }, [agentId, path, kind]);

  if (error) {
    return (
      <div className={styles.viewerEmpty}>
        <p style={{ color: "var(--fn-text-tertiary)", margin: 0 }}>
          {t("workspace.mediaLoadFailed", "无法加载预览")}
        </p>
      </div>
    );
  }

  // Legacy binary PPT is not an OOXML ZIP package and cannot be parsed by the
  // local PPTX renderer. Keep it private and offer a download instead of
  // sending authenticated workspace content to a third-party online viewer.
  if (kind === "ppt") {
    return (
      <div className={styles.viewerEmpty}>
        <p
          style={{
            color: "var(--fn-text-tertiary)",
            margin: "0 0 12px",
            textAlign: "center",
          }}
        >
          {t(
            "workspace.docPreviewUnsupported",
            "Online preview is not available for this document — please download it",
          )}
        </p>
        <Button
          type="primary"
          icon={<ArrowDownToLine size={14} />}
          onClick={() => void handleDownload()}
        >
          {t("common.download", "下载")}
        </Button>
      </div>
    );
  }

  if (kind === "pdf") {
    if (!src) {
      return (
        <div className={styles.viewerLoading}>
          <Spin />
        </div>
      );
    }
    return (
      <iframe
        title={path.split("/").filter(Boolean).pop() || "PDF"}
        src={src}
        className={styles.docFrame}
      />
    );
  }

  // Keep the target mounted while loading: Word, Excel and PPTX renderers write
  // directly into this element.
  return (
    <div className={styles.documentPreview}>
      <div
        className={
          kind === "word"
            ? styles.docxWrap
            : kind === "excel"
            ? styles.xlsxWrap
            : styles.pptxWrap
        }
        ref={containerRef}
      />
      {loading && (
        <div className={styles.documentLoading}>
          <Spin />
        </div>
      )}
    </div>
  );
}
