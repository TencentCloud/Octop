/**
 * GitDiffView — unified-diff renderer with line numbers and row tinting.
 * Pure presentational; parsing lives in parseUnifiedDiff for tests.
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "antd";
import styles from "../index.module.less";

export interface DiffRow {
  kind: "meta" | "hunk" | "add" | "del" | "ctx";
  oldNo: number | null;
  newNo: number | null;
  text: string;
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

export function parseUnifiedDiff(text: string): DiffRow[] {
  const rows: DiffRow[] = [];
  let oldNo = 0;
  let newNo = 0;
  for (const line of text.split("\n")) {
    if (!line) continue;
    if (line.startsWith("@@")) {
      const m = HUNK_RE.exec(line);
      if (m) {
        oldNo = Number(m[1]);
        newNo = Number(m[2]);
      }
      rows.push({ kind: "hunk", oldNo: null, newNo: null, text: line });
    } else if (
      line.startsWith("diff --git") ||
      line.startsWith("index ") ||
      line.startsWith("--- ") ||
      line.startsWith("+++ ") ||
      line.startsWith("old mode") ||
      line.startsWith("new mode") ||
      line.startsWith("similarity index") ||
      line.startsWith("rename from") ||
      line.startsWith("rename to") ||
      line.startsWith("copy from") ||
      line.startsWith("copy to") ||
      line.startsWith("Binary files") ||
      line.startsWith("new file mode") ||
      line.startsWith("deleted file mode") ||
      line.startsWith("\\")
    ) {
      rows.push({ kind: "meta", oldNo: null, newNo: null, text: line });
    } else if (line.startsWith("+")) {
      rows.push({ kind: "add", oldNo: null, newNo: newNo++, text: line });
    } else if (line.startsWith("-")) {
      rows.push({ kind: "del", oldNo: oldNo++, newNo: null, text: line });
    } else {
      rows.push({
        kind: "ctx",
        oldNo: oldNo++,
        newNo: newNo++,
        text: line,
      });
    }
  }
  return rows;
}

interface GitDiffViewProps {
  diff: string;
  truncated?: boolean;
}

export default function GitDiffView({ diff, truncated }: GitDiffViewProps) {
  const { t } = useTranslation();
  const rows = useMemo(() => parseUnifiedDiff(diff), [diff]);

  if (!diff.trim()) {
    return (
      <div className={styles.gitDiffEmpty}>
        {t("git.emptyDiff", "没有差异")}
      </div>
    );
  }

  return (
    <div className={styles.gitDiffWrap}>
      {truncated && (
        <Alert
          type="warning"
          showIcon
          message={t("git.diffTruncated", "差异过大，已截断显示")}
          className={styles.gitDiffTruncated}
        />
      )}
      <div className={styles.gitDiff}>
        <div className={styles.gitDiffRows}>
          {rows.map((row, i) => (
            <div
              key={i}
              className={`${styles.gitDiffRow} ${
                styles[`gitDiffRow_${row.kind}`] ?? ""
              }`}
            >
              <span className={styles.gitDiffNo}>{row.oldNo ?? ""}</span>
              <span className={styles.gitDiffNo}>{row.newNo ?? ""}</span>
              <span className={styles.gitDiffText}>{row.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
