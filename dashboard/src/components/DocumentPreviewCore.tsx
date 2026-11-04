/** Shared preview surface for PDF, Word, Excel and PowerPoint. */
import {
  useCallback,
  useEffect,
  lazy,
  Suspense,
  useRef,
  useState,
} from "react";
import { Button } from "antd";
import { ArrowDownToLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import {
  isNotFoundApiError,
  isOfficePreviewFallbackError,
} from "../utils/apiError";
import { type DocKind } from "../utils/docKind";
import type { OfficePdfPreview } from "../utils/officePreview";
import styles from "./DocumentPreviewCore.module.less";
import DocumentPreviewLoading from "./DocumentPreviewLoading";
import PdfDocumentPreview, { PdfViewerSkeleton } from "./PdfDocumentPreview";

import { parseExcel } from "./excelPreview/parse";
import type { ExcelPreview as ExcelPreviewData } from "./excelPreview/model";

const ExcelPreview = lazy(() => import("./excelPreview/ExcelPreview"));
const EXCEL_LIMITS = {
  maxBytes: 16 * 1024 * 1024,
  maxCells: 250_000,
  timeoutMs: 15_000,
};

export interface DocumentPreviewCoreProps {
  kind: DocKind;
  filename: string;
  fetchBlob: (
    onProgress?: (loaded: number, total: number) => void,
    signal?: AbortSignal,
  ) => Promise<Blob>;
  /** Authorized Office → PDF conversion. Callers own permission; this only loads. */
  fetchPdfPreview?: (
    onProgress?: (loaded: number, total: number) => void,
    signal?: AbortSignal,
  ) => Promise<OfficePdfPreview>;
  /** Optional download when the kind cannot be rendered (legacy ``.ppt`` / ``.doc``). */
  onDownload?: () => void | Promise<void>;
}

/** Office binaries with no in-browser renderer (legacy ``.ppt`` / ``.doc``). */
function isDownloadOnlyKind(kind: DocKind): boolean {
  return kind === "ppt" || kind === "doc";
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

const DOCX_MAX_LENGTH_PT = 2000;

const DOCX_ABSURD_LENGTH_RE =
  /(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)(pt|px|in|cm|mm)\b/gi;

function cssLengthToPt(value: number, unit: string): number | null {
  switch (unit.toLowerCase()) {
    case "pt":
      return value;
    case "px":
      return value * 0.75;
    case "in":
      return value * 72;
    case "cm":
      return value * 28.3465;
    case "mm":
      return value * 2.83465;
    default:
      return null;
  }
}

/**
 * Clamp absurd absolute lengths in an inline ``style`` attribute.
 *
 * Some DOCX files emit ``min-height`` / ``line-height`` near ``2^31`` twips
 * (≈ ``2.68e7pt``). docx-preview paints those literally, exploding the page to
 * tens of millions of pixels and shoving body text into a thin right-hand strip.
 */
export function clampAbsurdDocxCssLengths(style: string): string {
  if (
    !/(?:min-height|line-height|height|width|margin|padding|top|left|font-size)/i.test(
      style,
    )
  ) {
    return style;
  }
  return style.replace(
    DOCX_ABSURD_LENGTH_RE,
    (match, num: string, unit: string) => {
      const n = Number(num);
      if (!Number.isFinite(n)) return match;
      const pt = cssLengthToPt(n, unit);
      if (pt == null || Math.abs(pt) <= DOCX_MAX_LENGTH_PT) return match;
      return `0${unit}`;
    },
  );
}

/** docx-preview injects ``background: gray`` into a ``<style>`` tag — rewrite it. */
function neutralizeDocxPreviewChrome(root: HTMLElement): void {
  for (const style of root.querySelectorAll("style")) {
    const text = style.textContent;
    if (!text || !/background:\s*gray/i.test(text)) continue;
    style.textContent = text
      .replace(
        /background:\s*gray/gi,
        "background: var(--fn-bg-container, #fff)",
      )
      .replace(
        /box-shadow:\s*0 0 10px rgba\(0,\s*0,\s*0,\s*0\.5\)/gi,
        "box-shadow: none",
      );
  }
  for (const el of root.querySelectorAll<HTMLElement>(
    ".docx-doc-wrapper, .docx-wrapper",
  )) {
    el.style.setProperty(
      "background",
      "var(--fn-bg-container, #fff)",
      "important",
    );
  }
}

/** Post-process rendered DOCX DOM for known layout explosions. */
function sanitizeDocxPreviewLayout(root: HTMLElement): void {
  for (const el of root.querySelectorAll<HTMLElement>("[style]")) {
    const style = el.getAttribute("style");
    if (!style) continue;
    const next = clampAbsurdDocxCssLengths(style);
    if (next !== style) el.setAttribute("style", next);
  }
}

/**
 * Read a sheet cell-by-cell over ``!ref`` so every row has the same column
 * count (SheetJS ``sheet_to_json`` can drop leading empties / jagged rows).
 */
export default function DocumentPreviewCore({
  kind,
  filename,
  fetchBlob,
  fetchPdfPreview,
  onDownload,
}: DocumentPreviewCoreProps) {
  const { t } = useTranslation();
  const [src, setSrc] = useState("");
  /** Real download percent (0-100) while the blob streams in. */
  const [downloadPercent, setDownloadPercent] = useState<number | null>(null);
  const onBlobProgress = useCallback((loaded: number, total: number) => {
    if (total > 0) setDownloadPercent((loaded / total) * 100);
  }, []);
  const [loading, setLoading] = useState(true);
  const [loadPhase, setLoadPhase] = useState<"file" | "parse" | "convert">(
    "file",
  );
  const [officePdf, setOfficePdf] = useState(false);
  const [missingFonts, setMissingFonts] = useState<string[]>([]);
  const [error, setError] = useState<"missing" | "error" | null>(null);
  const [empty, setEmpty] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [excel, setExcel] = useState<ExcelPreviewData>();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const objectUrlRef = useRef<string | undefined>(undefined);
  const pptxViewerRef = useRef<{ destroy: () => void } | null>(null);

  const handleDownload = useCallback(() => {
    void onDownload?.();
  }, [onDownload]);

  const handleRetry = useCallback(() => {
    setError(null);
    setReloadNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadPhase("file");
    setDownloadPercent(null);
    setError(null);
    setEmpty(false);
    setSrc("");
    setOfficePdf(false);
    setMissingFonts([]);
    setExcel(undefined);
    pptxViewerRef.current?.destroy();
    pptxViewerRef.current = null;
    if (containerRef.current) containerRef.current.innerHTML = "";

    const abortController = new AbortController();
    const tryPdf =
      Boolean(fetchPdfPreview) && kind !== "pdf" && kind !== "excel";

    const load = async () => {
      try {
        if (tryPdf && fetchPdfPreview) {
          setLoadPhase("convert");
          try {
            const preview = await fetchPdfPreview(
              onBlobProgress,
              abortController.signal,
            );
            if (cancelled) return;
            const objUrl = URL.createObjectURL(preview.blob);
            objectUrlRef.current = objUrl;
            setSrc(objUrl);
            setOfficePdf(true);
            setMissingFonts(preview.missingFonts);
            setLoading(false);
            return;
          } catch (err) {
            if (cancelled || isAbortError(err)) return;
            if (!isOfficePreviewFallbackError(err)) {
              setError(isNotFoundApiError(err) ? "missing" : "error");
              setLoading(false);
              return;
            }
          }
        }

        if (isDownloadOnlyKind(kind)) {
          setLoading(false);
          return;
        }

        setLoadPhase("file");
        const blob = await fetchBlob(onBlobProgress, abortController.signal);
        if (cancelled) return;
        setLoadPhase("parse");
        setDownloadPercent(null);

        if (kind === "pdf") {
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
          if (buf.byteLength === 0) {
            if (!cancelled) setEmpty(true);
            if (!cancelled) setLoading(false);
            return;
          }
          const { renderAsync } = await import("docx-preview");
          if (containerRef.current && !cancelled) {
            await renderAsync(buf, containerRef.current, undefined, {
              className: "docx-doc",
              inWrapper: true,
              breakPages: true,
              ignoreWidth: false,
              ignoreHeight: false,
              useBase64URL: true,
            });
            if (!cancelled && containerRef.current) {
              neutralizeDocxPreviewChrome(containerRef.current);
              sanitizeDocxPreviewLayout(containerRef.current);
            }
          }
        } else if (kind === "excel") {
          const workbook = await parseExcel(
            new Uint8Array(buf),
            /\.xls$/i.test(filename) ? "xls" : "xlsx",
            EXCEL_LIMITS,
            abortController.signal,
          );
          if (!cancelled) setExcel(workbook);
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
      } catch (err) {
        if (cancelled || isAbortError(err)) return;
        // Surface the real cause (chunk load / ZIP parse / library error) —
        // the UI only shows a generic "无法加载预览".
        console.error(
          "[DocumentPreviewCore] preview failed",
          { kind, filename },
          err,
        );
        setError(isNotFoundApiError(err) ? "missing" : "error");
        setLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
      abortController.abort();
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = undefined;
      }
      pptxViewerRef.current?.destroy();
      pptxViewerRef.current = null;
    };
  }, [kind, filename, fetchBlob, fetchPdfPreview, reloadNonce, onBlobProgress]);

  if (empty) {
    return (
      <div className={styles.viewerEmpty}>
        <p style={{ color: "var(--fn-text-tertiary)", margin: 0 }}>
          {t("workspace.emptyFile", "文件为空")}
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.viewerEmpty}>
        <p
          style={{
            color: "var(--fn-text-tertiary)",
            margin: "0 0 12px",
            textAlign: "center",
          }}
        >
          {error === "missing"
            ? t("workspace.fileMaybeDeleted", "文件可能已被删除")
            : t("workspace.mediaLoadFailed", "无法加载预览")}
        </p>
        <Button type="default" onClick={handleRetry}>
          {t("workspace.retryPreview", "Retry")}
        </Button>
      </div>
    );
  }

  if (isDownloadOnlyKind(kind) && !officePdf) {
    if (loading) {
      return (
        <div className={styles.documentPreview}>
          <DocumentPreviewLoading
            phase={loadPhase}
            percent={
              loadPhase === "file" || loadPhase === "convert"
                ? downloadPercent
                : null
            }
          />
        </div>
      );
    }
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
        {onDownload ? (
          <Button
            type="primary"
            icon={<ArrowDownToLine size={14} />}
            onClick={handleDownload}
          >
            {t("common.download", "下载")}
          </Button>
        ) : null}
      </div>
    );
  }

  if (kind === "pdf" || officePdf) {
    if (!src) {
      // Progress-bar skeleton while the blob downloads (large files take seconds).
      return (
        <div className={styles.documentPreview}>
          <PdfViewerSkeleton percent={downloadPercent} />
        </div>
      );
    }
    return (
      <div className={styles.documentPreview}>
        {missingFonts.length > 0 ? (
          <div className={styles.officePreviewBar}>
            <p className={styles.officePreviewHint}>
              {t(
                "workspace.officeMissingFonts",
                "Some fonts were substituted in this preview",
              )}
            </p>
          </div>
        ) : null}
        <PdfDocumentPreview fileUrl={src} filename={filename} />
      </div>
    );
  }

  if (kind === "excel") {
    const loadingView = (
      <DocumentPreviewLoading phase={loadPhase} percent={downloadPercent} />
    );
    return (
      <div className={styles.documentPreview}>
        <Suspense fallback={loadingView}>
          {excel ? <ExcelPreview preview={excel} /> : loadingView}
        </Suspense>
      </div>
    );
  }

  return (
    <div className={styles.documentPreview}>
      <div
        className={kind === "word" ? styles.docxWrap : styles.pptxWrap}
        ref={containerRef}
      />
      <div
        className={cx(
          styles.documentLoading,
          !loading && styles.documentLoadingHidden,
        )}
        aria-hidden={!loading}
      >
        <DocumentPreviewLoading
          phase={loadPhase}
          percent={loadPhase === "file" ? downloadPercent : null}
        />
      </div>
    </div>
  );
}
