import { useEffect, useRef } from "react";
import { Workbook } from "@fortune-sheet/react";
import { useTranslation } from "react-i18next";
import fortuneCss from "@fortune-sheet/react/dist/index.css?inline";
import type { ExcelPreview as Preview } from "./model";
import styles from "./ExcelPreview.module.less";

const scopedStyles = `@scope ([data-octop-excel-preview]) { ${fortuneCss} }`;

export default function ExcelPreview({ preview }: { preview: Preview }) {
  const { t, i18n } = useTranslation();
  const grid = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!grid.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() =>
      window.dispatchEvent(new Event("resize")),
    );
    observer.observe(grid.current);
    return () => observer.disconnect();
  }, []);

  return (
    <section className={styles.preview} data-octop-excel-preview>
      <style>{scopedStyles}</style>
      {preview.unsupportedFeatures.length > 0 && (
        <div className={styles.notice} role="note">
          {t("workspace.excelUnsupportedPreview")}
        </div>
      )}
      {preview.missingResults > 0 && (
        <div className={styles.notice} role="note">
          {t("workspace.excelMissingFormulaResults")}
        </div>
      )}
      <div className={styles.grid} ref={grid}>
        <Workbook
          data={preview.sheets}
          lang={i18n.language?.startsWith("zh") ? "zh" : "en"}
          allowEdit={false}
          showToolbar={false}
          showFormulaBar
          showSheetTabs
          forceCalculation={false}
          cellContextMenu={["copy"]}
          headerContextMenu={[]}
          sheetTabContextMenu={[]}
          filterContextMenu={[]}
        />
      </div>
    </section>
  );
}
