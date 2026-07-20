/**
 * Classify rich document files (PDF / Office) by extension.
 *
 * These are neither plain text (editable in Monaco) nor media
 * (image/video/audio), so the workspace viewer renders them through a
 * dedicated document preview surface.
 */

export type DocKind = "pdf" | "word" | "excel" | "pptx" | "ppt";

const WORD_EXT = new Set(["docx", "doc"]);
const EXCEL_EXT = new Set(["xlsx", "xls"]);

export function getDocKind(path: string): DocKind | null {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "pdf";
  if (WORD_EXT.has(ext)) return "word";
  if (EXCEL_EXT.has(ext)) return "excel";
  if (ext === "pptx") return "pptx";
  if (ext === "ppt") return "ppt";
  return null;
}
