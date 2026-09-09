/**
 * Framework-agnostic rich document renderer (PDF / Word / Excel / PPTX).
 *
 * Excel path: SheetJS parses the workbook → native HTML table (+ Ant Design
 * ``Tabs``). Embedded ``xl/media`` images are extracted as ``data:`` URLs and
 * shown in screenshot-like columns via Ant Design ``Image``.
 *
 * Native ``<table>`` (not Ant Design ``Table``) keeps header/body column
 * widths in one layout tree — avoids the classic antd scroll/ellipsis drift.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Image, Spin, Tabs } from "antd";
import { ArrowDownToLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { isNotFoundApiError } from "../utils/apiError";
import type { DocKind } from "../utils/docKind";
import styles from "./DocumentPreviewCore.module.less";
import PdfDocumentPreview from "./PdfDocumentPreview";

export interface DocumentPreviewCoreProps {
  kind: DocKind;
  filename: string;
  fetchBlob: () => Promise<Blob>;
  /** Optional download when the kind cannot be rendered (e.g. legacy ``.ppt``). */
  onDownload?: () => void | Promise<void>;
}

interface ExcelSheetData {
  name: string;
  /** First row is header; remaining rows are body cells as strings. */
  matrix: string[][];
}

interface ExcelMediaItem {
  name: string;
  /** ``data:image/...;base64,...`` */
  dataUrl: string;
}

interface ExcelColumn {
  key: string;
  title: string;
  width: number;
  isImageCol: boolean;
  /** Absorb leftover table width so blank columns stay narrow. */
  flexible: boolean;
}

interface ExcelTableModel {
  columns: ExcelColumn[];
  /** Body rows only; each ``cells`` array is padded to ``columns.length``. */
  rows: { key: string; rowIndex: number; cells: string[] }[];
  scrollX: number;
}

const EXCEL_MAX_COLS = 40;
const EXCEL_MAX_ROWS = 500;

function cellLooksLikeImageRef(value: string): boolean {
  const v = value.trim();
  if (!v) return false;
  if (/DISPIMG/i.test(v)) return true;
  if (/\.(png|jpe?g|gif|webp|bmp)$/i.test(v)) return true;
  if (/^image\./i.test(v)) return true;
  return false;
}

function columnLooksLikeImage(title: string): boolean {
  return /截图|设计稿|图片|image|screenshot|photo|附图|缩略图|draft/i.test(
    title,
  );
}

/** Drop leading/trailing columns that have no header and no cell values. */
function trimEmptyMatrixColumns(matrix: string[][]): string[][] {
  if (matrix.length === 0) return matrix;
  const colCount = Math.max(0, ...matrix.map((row) => row.length));
  if (colCount === 0) return matrix;

  const colHasContent = Array.from({ length: colCount }, (_, index) =>
    matrix.some((row) => (row[index] ?? "").trim().length > 0),
  );
  let start = 0;
  while (start < colCount && !colHasContent[start]) start += 1;
  let end = colCount - 1;
  while (end >= start && !colHasContent[end]) end -= 1;
  if (start === 0 && end === colCount - 1) return matrix;
  if (start > end) return matrix.map(() => [] as string[]);
  return matrix.map((row) => row.slice(start, end + 1));
}

function mimeForMediaName(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "png") return "image/png";
  if (ext === "jpg" || ext === "jpeg") return "image/jpeg";
  if (ext === "gif") return "image/gif";
  if (ext === "webp") return "image/webp";
  if (ext === "bmp") return "image/bmp";
  return "application/octet-stream";
}

async function extractXlsxMediaDataUrls(
  buf: ArrayBuffer,
): Promise<ExcelMediaItem[]> {
  const JSZip = (await import("jszip")).default;
  const zip = await JSZip.loadAsync(buf);
  const paths = Object.keys(zip.files)
    .filter((path) => path.startsWith("xl/media/") && !zip.files[path]?.dir)
    .sort();
  const items: ExcelMediaItem[] = [];
  for (const path of paths) {
    const entry = zip.files[path];
    if (!entry) continue;
    const name = path.split("/").pop() || path;
    const mime = mimeForMediaName(name);
    if (!mime.startsWith("image/")) continue;
    const base64 = await entry.async("base64");
    items.push({ name, dataUrl: `data:${mime};base64,${base64}` });
  }
  return items;
}

/** Absolute lengths beyond this (≈ 27″) are treated as corrupt DOCX metrics. */
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
      .replace(/background:\s*gray/gi, "background: #fff")
      .replace(
        /box-shadow:\s*0 0 10px rgba\(0,\s*0,\s*0,\s*0\.5\)/gi,
        "box-shadow: none",
      );
  }
  for (const el of root.querySelectorAll<HTMLElement>(
    ".docx-doc-wrapper, .docx-wrapper",
  )) {
    el.style.setProperty("background", "#fff", "important");
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
function sheetToMatrix(
  xlsx: typeof import("xlsx"),
  sheet: import("xlsx").WorkSheet,
): string[][] {
  const ref = sheet["!ref"];
  if (!ref) return [];
  const range = xlsx.utils.decode_range(ref);
  const endRow = Math.min(range.e.r, range.s.r + EXCEL_MAX_ROWS);
  const endCol = Math.min(range.e.c, range.s.c + EXCEL_MAX_COLS - 1);
  const matrix: string[][] = [];
  for (let row = range.s.r; row <= endRow; row += 1) {
    const cells: string[] = [];
    for (let col = range.s.c; col <= endCol; col += 1) {
      const addr = xlsx.utils.encode_cell({ r: row, c: col });
      const cell = sheet[addr];
      cells.push(cell == null ? "" : String(xlsx.utils.format_cell(cell)));
    }
    matrix.push(cells);
  }
  return matrix;
}

function buildExcelTable(sheet: ExcelSheetData): ExcelTableModel {
  const matrix = trimEmptyMatrixColumns(sheet.matrix);
  const header = matrix[0] ?? [];
  const body = matrix.slice(1);
  const colCount = Math.max(
    header.length,
    ...matrix.map((row) => row.length),
    1,
  );

  // Prefer mapping media into the first screenshot-like column by row order.
  let imageCol = -1;
  for (let index = 0; index < colCount; index += 1) {
    if (columnLooksLikeImage((header[index] || "").trim())) {
      imageCol = index;
      break;
    }
  }
  if (imageCol < 0) {
    for (let index = 0; index < colCount; index += 1) {
      if (body.some((row) => cellLooksLikeImageRef(row[index] ?? ""))) {
        imageCol = index;
        break;
      }
    }
  }

  const columns: ExcelColumn[] = Array.from(
    { length: colCount },
    (_, index) => {
      const title = (header[index] || "").trim() || `Col ${index + 1}`;
      const isImageCol = index === imageCol || columnLooksLikeImage(title);
      const hasBody = body.some((row) => (row[index] ?? "").trim().length > 0);
      let width: number;
      if (isImageCol) {
        width = 168;
      } else if (!hasBody) {
        // Header-only / blank columns should stay narrow so text cols can breathe.
        width = Math.min(120, Math.max(72, title.length * 14));
      } else {
        const sampleLen = Math.max(
          title.length,
          ...body.slice(0, 40).map((row) => (row[index] ?? "").trim().length),
        );
        width = Math.min(360, Math.max(160, sampleLen * 12));
      }
      return {
        key: `c${index}`,
        title,
        width,
        isImageCol,
        flexible: false,
      };
    },
  );

  // Last non-image column with content absorbs leftover width when table is 100%.
  for (let index = columns.length - 1; index >= 0; index -= 1) {
    const col = columns[index];
    if (col && !col.isImageCol) {
      col.flexible = true;
      break;
    }
  }

  const rows = body.map((row, rowIndex) => ({
    key: String(rowIndex),
    rowIndex,
    cells: Array.from({ length: colCount }, (_, index) => row[index] ?? ""),
  }));

  const scrollX = columns.reduce((sum, col) => sum + col.width, 0);
  return { columns, rows, scrollX };
}

function ExcelCellContent({
  text,
  isImageCol,
  mediaItem,
}: {
  text: string;
  isImageCol: boolean;
  mediaItem?: ExcelMediaItem;
}) {
  if (mediaItem) {
    return (
      <Image
        src={mediaItem.dataUrl}
        alt={mediaItem.name}
        className={styles.xlsxCellThumb}
        preview={{ src: mediaItem.dataUrl }}
      />
    );
  }
  if (cellLooksLikeImageRef(text) || (isImageCol && !text.trim())) {
    return <span className={styles.xlsxImageCell}>—</span>;
  }
  return text;
}

export default function DocumentPreviewCore({
  kind,
  filename,
  fetchBlob,
  onDownload,
}: DocumentPreviewCoreProps) {
  const { t } = useTranslation();
  const [src, setSrc] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"missing" | "error" | null>(null);
  const [empty, setEmpty] = useState(false);
  const [excelSheets, setExcelSheets] = useState<ExcelSheetData[]>([]);
  const [excelTab, setExcelTab] = useState("0");
  const [excelTruncated, setExcelTruncated] = useState(false);
  const [excelMedia, setExcelMedia] = useState<ExcelMediaItem[]>([]);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const objectUrlRef = useRef<string | undefined>(undefined);
  const pptxViewerRef = useRef<{ destroy: () => void } | null>(null);

  const handleDownload = useCallback(() => {
    void onDownload?.();
  }, [onDownload]);

  const activeSheet = useMemo(() => {
    const index = Number(excelTab);
    return excelSheets[Number.isFinite(index) ? index : 0] ?? null;
  }, [excelSheets, excelTab]);

  const activeTable = useMemo(() => {
    if (!activeSheet) return null;
    return buildExcelTable(activeSheet);
  }, [activeSheet]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setEmpty(false);
    setSrc("");
    setExcelSheets([]);
    setExcelTab("0");
    setExcelTruncated(false);
    setExcelMedia([]);
    pptxViewerRef.current?.destroy();
    pptxViewerRef.current = null;
    if (containerRef.current) containerRef.current.innerHTML = "";
    if (kind === "ppt") {
      setLoading(false);
      return;
    }

    const load = async () => {
      try {
        const blob = await fetchBlob();
        if (cancelled) return;

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
          const xlsx = await import("xlsx");
          const wb = xlsx.read(buf, { type: "array", cellDates: true });
          let truncated = false;
          const sheets: ExcelSheetData[] = wb.SheetNames.map((name) => {
            const sheet = wb.Sheets[name];
            if (!sheet) return { name, matrix: [] as string[][] };
            const ref = sheet["!ref"];
            if (ref) {
              const range = xlsx.utils.decode_range(ref);
              if (
                range.e.r - range.s.r > EXCEL_MAX_ROWS ||
                range.e.c - range.s.c + 1 > EXCEL_MAX_COLS
              ) {
                truncated = true;
              }
            }
            return { name, matrix: sheetToMatrix(xlsx, sheet) };
          });
          let media: ExcelMediaItem[] = [];
          try {
            media = await extractXlsxMediaDataUrls(buf);
          } catch {
            media = [];
          }
          if (!cancelled) {
            const hasCells = sheets.some((sheet) =>
              sheet.matrix.some((row) =>
                row.some((cell) => String(cell).trim().length > 0),
              ),
            );
            if (!hasCells && media.length === 0) {
              setEmpty(true);
            } else {
              setExcelSheets(sheets);
              setExcelTab("0");
              setExcelTruncated(truncated);
              setExcelMedia(media);
            }
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
      } catch (err) {
        if (!cancelled) {
          setError(isNotFoundApiError(err) ? "missing" : "error");
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
  }, [kind, fetchBlob]);

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
        <p style={{ color: "var(--fn-text-tertiary)", margin: 0 }}>
          {error === "missing"
            ? t("workspace.fileMaybeDeleted", "文件可能已被删除")
            : t("workspace.mediaLoadFailed", "无法加载预览")}
        </p>
      </div>
    );
  }

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

  if (kind === "pdf") {
    if (!src) {
      return (
        <div className={styles.viewerLoading}>
          <Spin />
        </div>
      );
    }
    return (
      <div className={styles.documentPreview}>
        <PdfDocumentPreview fileUrl={src} filename={filename} />
      </div>
    );
  }

  if (kind === "excel") {
    return (
      <div className={styles.documentPreview}>
        <div className={styles.xlsxWrap}>
          {excelSheets.length > 1 ? (
            <Tabs
              size="small"
              activeKey={excelTab}
              onChange={setExcelTab}
              items={excelSheets.map((sheet, index) => ({
                key: String(index),
                label: sheet.name,
              }))}
            />
          ) : null}
          {excelTruncated ? (
            <p className={styles.xlsxHint}>
              {t(
                "workspace.excelPreviewTruncated",
                "Preview shows the first {{rows}} rows and {{cols}} columns — download for the full sheet",
                { rows: EXCEL_MAX_ROWS, cols: EXCEL_MAX_COLS },
              )}
            </p>
          ) : null}
          {activeTable ? (
            <div className={styles.xlsxTableHost}>
              <table
                className={styles.xlsxTable}
                style={{ minWidth: activeTable.scrollX }}
              >
                <colgroup>
                  {activeTable.columns.map((col) => (
                    <col
                      key={col.key}
                      style={
                        col.flexible
                          ? { minWidth: col.width }
                          : { width: col.width }
                      }
                    />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    {activeTable.columns.map((col) => (
                      <th key={col.key} title={col.title}>
                        {col.title}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {activeTable.rows.map((row) => (
                    <tr key={row.key}>
                      {activeTable.columns.map((col, colIndex) => {
                        const text = row.cells[colIndex] ?? "";
                        const mediaItem = col.isImageCol
                          ? excelMedia[row.rowIndex]
                          : undefined;
                        return (
                          <td
                            key={col.key}
                            className={
                              col.isImageCol
                                ? styles.xlsxImageTd
                                : styles.xlsxTextTd
                            }
                            title={
                              col.isImageCol || mediaItem ? undefined : text
                            }
                          >
                            <ExcelCellContent
                              text={text}
                              isImageCol={col.isImageCol}
                              mediaItem={mediaItem}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
        {loading && (
          <div className={styles.documentLoading}>
            <Spin />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={styles.documentPreview}>
      <div
        className={kind === "word" ? styles.docxWrap : styles.pptxWrap}
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
