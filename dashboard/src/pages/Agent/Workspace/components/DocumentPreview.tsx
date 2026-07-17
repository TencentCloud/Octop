/**
 * DocumentPreview — render rich documents (PDF / Word / Excel) inside the
 * workspace viewer.
 *
 * PDFs are shown with the browser's native viewer via an ``<iframe>``.
 * Word (``.docx``) is rendered with ``docx-preview`` and Excel (``.xlsx``)
 * is parsed by SheetJS and rendered as HTML tables. Both heavy libraries are
 * dynamically imported so they only ship when such a file is actually opened.
 *
 * The file bytes are fetched through the authenticated ``requestBlob`` helper.
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
    if (containerRef.current) containerRef.current.innerHTML = "";

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
                `<div class="${styles.xlsxSheetTitle}">${escapeHtml(name)}</div>` +
                html +
                "</div>"
              );
            }).join("");
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

  // Presentation files (PPT / PPTX) can't be rendered in-browser without a
  // heavyweight converter, so offer a download instead of a blank frame.
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

  if (loading) {
    return (
      <div className={styles.viewerLoading}>
        <Spin />
      </div>
    );
  }

  // Word and Excel are mounted into this scroll container.
  return (
    <div
      className={kind === "word" ? styles.docxWrap : styles.xlsxWrap}
      ref={containerRef}
    />
  );
}
