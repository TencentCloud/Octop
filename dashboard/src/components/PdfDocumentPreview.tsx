/**
 * In-app PDF viewer via Mozilla PDF.js (react-pdf) — avoids Chrome's iframe
 * chrome and keeps look/controls consistent across browsers.
 */

import { useEffect, useRef, useState } from "react";
import { Button, Spin } from "antd";
import { Minus, Plus, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Document, Page, pdfjs } from "react-pdf";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import styles from "./PdfDocumentPreview.module.less";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;
const ZOOM_STEP = 0.1;

interface PdfDocumentPreviewProps {
  fileUrl: string;
  filename: string;
}

export default function PdfDocumentPreview({
  fileUrl,
  filename,
}: PdfDocumentPreviewProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageWidth, setPageWidth] = useState(720);
  const [zoom, setZoom] = useState(1);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => {
      const next = Math.floor(el.clientWidth - 32);
      if (next > 0) setPageWidth(next);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setNumPages(0);
    setLoadFailed(false);
    setZoom(1);
  }, [fileUrl]);

  const renderWidth = Math.max(120, Math.floor(pageWidth * zoom));

  return (
    <div className={styles.pdfPreview}>
      <div className={styles.pdfToolbar}>
        <div className={styles.pdfToolbarGroup}>
          <Button
            type="text"
            size="small"
            icon={<Minus size={14} />}
            aria-label={t("workspace.pdfZoomOut", "Zoom out")}
            disabled={zoom <= MIN_ZOOM}
            onClick={() =>
              setZoom((value) => Math.max(MIN_ZOOM, value - ZOOM_STEP))
            }
          />
          <span className={styles.pdfZoomLabel}>{Math.round(zoom * 100)}%</span>
          <Button
            type="text"
            size="small"
            icon={<Plus size={14} />}
            aria-label={t("workspace.pdfZoomIn", "Zoom in")}
            disabled={zoom >= MAX_ZOOM}
            onClick={() =>
              setZoom((value) => Math.min(MAX_ZOOM, value + ZOOM_STEP))
            }
          />
          <Button
            type="text"
            size="small"
            icon={<RotateCcw size={14} />}
            aria-label={t("workspace.pdfZoomReset", "Reset zoom")}
            disabled={zoom === 1}
            onClick={() => setZoom(1)}
          />
        </div>
        {numPages > 0 ? (
          <span className={styles.pdfMeta}>
            {t("workspace.pdfPageCount", "{{count}} pages", {
              count: numPages,
            })}
          </span>
        ) : null}
      </div>
      <div className={styles.pdfScroll} ref={scrollRef}>
        {loadFailed ? (
          <div className={styles.pdfEmpty}>
            {t("workspace.mediaLoadFailed", "Could not load preview")}
          </div>
        ) : (
          <Document
            file={fileUrl}
            loading={
              <div className={styles.pdfLoading}>
                <Spin />
              </div>
            }
            onLoadSuccess={(pdf) => {
              setNumPages(pdf.numPages);
              setLoadFailed(false);
            }}
            onLoadError={() => {
              setLoadFailed(true);
              setNumPages(0);
            }}
            className={styles.pdfDocument}
          >
            {Array.from({ length: numPages }, (_, index) => (
              <Page
                key={`${filename}-${index + 1}`}
                pageNumber={index + 1}
                width={renderWidth}
                className={styles.pdfPage}
                renderTextLayer
                renderAnnotationLayer
                loading={
                  <div
                    className={styles.pdfPageSkeleton}
                    style={{ width: renderWidth, minHeight: renderWidth * 1.3 }}
                  />
                }
              />
            ))}
          </Document>
        )}
      </div>
    </div>
  );
}
