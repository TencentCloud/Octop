import { useEffect, useState } from "react";
import { Button, Image, Tabs } from "antd";
import { useTranslation } from "react-i18next";
import type { DocumentPreviewCoreProps } from "./DocumentPreviewCore";
import DocumentPreviewLoading from "./DocumentPreviewLoading";
import { isNotFoundApiError } from "../utils/apiError";
import {
  EXCEL_MAX_COLS,
  EXCEL_MAX_ROWS,
  parseExcelPreview,
  type PreviewWorkbook,
} from "./excelPreviewModel";
import styles from "./ExcelDocumentPreview.module.less";

export default function ExcelDocumentPreview({
  filename,
  fetchBlob,
  onDownload,
}: DocumentPreviewCoreProps) {
  const { t } = useTranslation();
  const [workbook, setWorkbook] = useState<PreviewWorkbook | null>(null);
  const [active, setActive] = useState("0");
  const [phase, setPhase] = useState<"file" | "parse">("file");
  const [percent, setPercent] = useState<number | null>(null);
  const [error, setError] = useState<"missing" | "error" | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setWorkbook(null);
    setActive("0");
    setError(null);
    setPercent(null);
    setPhase("file");
    void (async () => {
      try {
        const blob = await fetchBlob((loaded, total) => {
          if (!controller.signal.aborted && total > 0)
            setPercent((loaded / total) * 100);
        }, controller.signal);
        if (controller.signal.aborted) return;
        setPhase("parse");
        const result = await parseExcelPreview(
          await blob.arrayBuffer(),
          filename,
        );
        if (!controller.signal.aborted) setWorkbook(result);
      } catch (err) {
        if (!controller.signal.aborted)
          setError(isNotFoundApiError(err) ? "missing" : "error");
      }
    })();
    return () => controller.abort();
  }, [fetchBlob, filename, retry]);
  const sheet = workbook?.sheets[Number(active)];
  const uncalculated = sheet?.rows.some((row) =>
    row.cells.some((cell) => cell.formula),
  );
  return (
    <div className={styles.preview}>
      {error ? (
        <div className={styles.empty} role="alert">
          <p>
            {t(
              error === "missing"
                ? "workspace.fileMaybeDeleted"
                : "workspace.mediaLoadFailed",
            )}
          </p>
          <Button onClick={() => setRetry((n) => n + 1)}>
            {t("workspace.retryPreview")}
          </Button>
          {onDownload && (
            <Button onClick={() => void onDownload()}>
              {t("common.download")}
            </Button>
          )}
        </div>
      ) : !workbook ? (
        <DocumentPreviewLoading
          phase={phase}
          percent={phase === "file" ? percent : null}
        />
      ) : (
        <>
          {workbook.sheets.length > 1 && (
            <Tabs
              size="small"
              activeKey={active}
              onChange={setActive}
              items={workbook.sheets.map((item, index) => ({
                key: String(index),
                label: item.name,
              }))}
            />
          )}
          {sheet?.truncated && (
            <p className={styles.hint}>
              {t("workspace.excelPreviewTruncated", {
                rows: EXCEL_MAX_ROWS,
                cols: EXCEL_MAX_COLS,
              })}
            </p>
          )}
          {uncalculated && (
            <p className={styles.hint}>
              {t("workspace.excelFormulaUncalculated")}
            </p>
          )}
          {sheet && (
            <div className={styles.scroll}>
              <table
                className={styles.sheet}
                aria-label={sheet.name}
                style={{
                  width: sheet.columns.reduce(
                    (sum, col) => sum + col.width,
                    44,
                  ),
                }}
              >
                <colgroup>
                  <col style={{ width: 44 }} />
                  {sheet.columns.map((col) => (
                    <col key={col.label} style={{ width: col.width }} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    <th aria-label={t("workspace.excelRowNumber")} />
                    {sheet.columns.map((col) => (
                      <th key={col.label} scope="col">
                        {col.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sheet.rows.map((row) => (
                    <tr key={row.number} style={{ height: row.height }}>
                      <th scope="row">{row.number}</th>
                      {row.cells.map((cell, index) =>
                        cell.covered ? null : (
                          <td
                            key={index}
                            rowSpan={cell.rowSpan}
                            colSpan={cell.colSpan}
                            style={cell.style}
                            title={cell.text}
                          >
                            {cell.text}
                          </td>
                        ),
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!sheet && <p>{t("workspace.emptyFile")}</p>}
          {workbook.media.length > 0 && (
            <div className={styles.gallery}>
              <p className={styles.hint}>
                {t("workspace.excelEmbeddedImages")}
              </p>
              <Image.PreviewGroup>
                {workbook.media.map((item) => (
                  <Image
                    key={item.name}
                    src={item.dataUrl}
                    alt={item.name}
                    width={120}
                    height={80}
                    style={{ objectFit: "contain" }}
                  />
                ))}
              </Image.PreviewGroup>
            </div>
          )}
        </>
      )}
    </div>
  );
}
