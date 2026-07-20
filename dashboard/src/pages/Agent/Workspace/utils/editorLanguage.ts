/**
 * Map a workspace file path to a Monaco editor language id.
 *
 * Falls back to "plaintext" for unknown or extension-less files so the
 * editor still renders instead of throwing.
 */

const EXT_LANGUAGE: Record<string, string> = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  json: "json",
  jsonl: "json",
  md: "markdown",
  markdown: "markdown",
  css: "css",
  less: "less",
  scss: "scss",
  html: "html",
  htm: "html",
  xml: "xml",
  svg: "xml",
  yaml: "yaml",
  yml: "yaml",
  toml: "ini",
  ini: "ini",
  env: "ini",
  sh: "shell",
  bash: "shell",
  zsh: "shell",
  sql: "sql",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  rb: "ruby",
  php: "php",
  c: "c",
  h: "c",
  cpp: "cpp",
  cc: "cpp",
  hpp: "cpp",
  cs: "csharp",
  swift: "swift",
  dockerfile: "dockerfile",
  csv: "plaintext",
  txt: "plaintext",
  log: "plaintext",
};

export function getEditorLanguage(path: string): string {
  const name = path.split("/").filter(Boolean).pop() ?? path;
  if (name.toLowerCase() === "dockerfile") return "dockerfile";
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return EXT_LANGUAGE[ext] ?? "plaintext";
}
