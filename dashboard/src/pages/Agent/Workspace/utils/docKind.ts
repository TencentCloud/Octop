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

/**
 * Documents editable online via a Markdown round-trip, mapped to the Monaco
 * language used while editing. Mirrors the backend converter registry in
 * ``src/octop/infra/utils/doc_edit.py`` — to enable a new extension, add it
 * here AND register a matching converter on the backend.
 */
const EDITABLE_DOCS: Record<string, string> = {
  docx: "markdown",
};

/** Whether a workspace file can be edited online (Markdown round-trip). */
export function isEditableDoc(path: string): boolean {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return Object.prototype.hasOwnProperty.call(EDITABLE_DOCS, ext);
}

/** Monaco language for an editable document, or ``null`` when not editable. */
export function getEditableDocLanguage(path: string): string | null {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return EDITABLE_DOCS[ext] ?? null;
}
