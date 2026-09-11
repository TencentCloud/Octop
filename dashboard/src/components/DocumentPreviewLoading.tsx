/**
 * Shared full-area loading state for document previews (PDF / Office / Markdown).
 * Prefer Spin + short tip over blank white canvases while bytes parse or pages paint.
 */

import { Progress, Spin } from "antd";
import { useTranslation } from "react-i18next";
import styles from "./DocumentPreviewLoading.module.less";

export type DocumentPreviewLoadingPhase = "file" | "parse" | "render";

interface DocumentPreviewLoadingProps {
  phase?: DocumentPreviewLoadingPhase;
  className?: string;
  /** Stretch to fill the preview host (default true). */
  fill?: boolean;
  /** Optional download percent (0-100) while bytes stream in. */
  percent?: number | null;
}

export default function DocumentPreviewLoading({
  phase = "file",
  className,
  fill = true,
  percent = null,
}: DocumentPreviewLoadingProps) {
  const { t } = useTranslation();
  const tip =
    phase === "parse"
      ? t("workspace.previewParsingDocument", "Parsing document…")
      : phase === "render"
      ? t("workspace.previewRenderingPages", "Loading document…")
      : t("workspace.previewLoadingFile", "Loading file…");
  const showPercent =
    phase === "file" && typeof percent === "number" && Number.isFinite(percent);

  return (
    <div
      className={[styles.root, fill ? styles.fill : "", className ?? ""]
        .filter(Boolean)
        .join(" ")}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <Spin size="large" />
      <p className={styles.tip}>{tip}</p>
      {showPercent ? (
        <Progress
          percent={Math.max(0, Math.min(100, Math.round(percent)))}
          size="small"
          className={styles.progress}
          aria-label={tip}
        />
      ) : null}
    </div>
  );
}
