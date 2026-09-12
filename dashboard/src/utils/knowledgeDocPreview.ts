/**
 * Pure helpers for knowledge-document preview / download affordances.
 * Shared by Knowledge Bases and Chat citation preview (no page imports).
 */

export function isEditableKnowledgeDocument(doc: {
  is_dir?: boolean;
  content_type?: string;
  filename?: string;
}): boolean {
  if (doc.is_dir) return false;
  const ct = (doc.content_type || "").toLowerCase();
  if (ct === "text/plain" || ct === "text/markdown") return true;
  const name = (doc.filename || "").toLowerCase();
  return name.endsWith(".md") || name.endsWith(".txt");
}

/**
 * Show download when the on-disk file is still available (upload or
 * in-app note). Missing originals (deleted from disk) stay hidden.
 */
export function canDownloadKnowledgeOriginal(doc: {
  is_dir?: boolean;
  has_original?: boolean;
  content_type?: string;
  filename?: string;
}): boolean {
  if (doc.is_dir) return false;
  if (doc.has_original === false) return false;
  return true;
}

/** Markdown files get rendered preview (not a raw ``<pre>`` dump). */
export function isKnowledgeMarkdownDocument(doc: {
  is_dir?: boolean;
  content_type?: string;
  filename?: string;
}): boolean {
  if (doc.is_dir) return false;
  const ct = (doc.content_type || "").toLowerCase();
  if (ct === "text/markdown") return true;
  const name = (doc.filename || "").toLowerCase();
  return name.endsWith(".md") || name.endsWith(".markdown");
}

function knowledgeDocumentExt(filename: string | undefined): string {
  const name = (filename || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1) : "";
}

/** Original-file rich viewers (DocumentPreviewCore). */
const RICH_PREVIEW_EXTS = new Set([
  "pdf",
  "doc",
  "docx",
  "pptx",
  "xls",
  "xlsx",
  "xlsm",
]);

/** UTF-8 / extracted-text preview (Markdown or ``<pre>``). */
const TEXT_PREVIEW_EXTS = new Set([
  "md",
  "markdown",
  "txt",
  "rst",
  "html",
  "htm",
  "json",
  "jsonl",
  "yaml",
  "yml",
  "csv",
  "tsv",
  // Legacy PowerPoint: no in-browser slide renderer — use extracted text.
  "ppt",
]);

/** Whether the Eye action should be enabled for this knowledge document. */
export function canPreviewKnowledgeDocument(doc: {
  is_dir?: boolean;
  content_type?: string;
  filename?: string;
  has_original?: boolean;
}): boolean {
  if (doc.is_dir) return false;
  if (isKnowledgeMarkdownDocument(doc) || isEditableKnowledgeDocument(doc)) {
    return true;
  }
  const ext = knowledgeDocumentExt(doc.filename);
  if (TEXT_PREVIEW_EXTS.has(ext)) return true;
  if (RICH_PREVIEW_EXTS.has(ext)) return true;
  return false;
}

/**
 * Open the original file in DocumentPreviewCore (PDF / DOCX / PPTX / Excel).
 * When false, preview falls back to extracted / UTF-8 text.
 *
 * Omit ``has_original`` (or leave undefined) when unknown — e.g. chat
 * citations — so extension alone can attempt rich preview with a 404 fallback.
 */
export function canRichPreviewKnowledgeDocument(doc: {
  filename?: string;
  has_original?: boolean;
}): boolean {
  if (doc.has_original === false) return false;
  return RICH_PREVIEW_EXTS.has(knowledgeDocumentExt(doc.filename));
}

/** Extension-only rich gate (unknown original); same set as rich preview. */
export function isRichPreviewFilename(filename: string | undefined): boolean {
  return RICH_PREVIEW_EXTS.has(knowledgeDocumentExt(filename));
}
