/**
 * Heuristics for classifying a workspace entry path.
 *
 * Kept separate from media/document classification so both the workspace
 * drawer and the shared ``FileViewer`` can reuse the same text-file test.
 */

const TEXT_EXTENSIONS = new Set([
  "astro",
  "c",
  "cfg",
  "clj",
  "cljs",
  "cmake",
  "conf",
  "cpp",
  "cs",
  "css",
  "csv",
  "dart",
  "env",
  "go",
  "gradle",
  "graphql",
  "groovy",
  "h",
  "hpp",
  "html",
  "ini",
  "java",
  "js",
  "json",
  "jsonl",
  "jsx",
  "kt",
  "kts",
  "less",
  "log",
  "lua",
  "md",
  "mdx",
  "php",
  "pl",
  "pm",
  "properties",
  "proto",
  "py",
  "r",
  "rb",
  "rs",
  "rst",
  "sass",
  "scala",
  "scss",
  "sh",
  "sql",
  "svelte",
  "swift",
  "tex",
  "toml",
  "ts",
  "tsx",
  "txt",
  "vue",
  "xml",
  "yaml",
  "yml",
  "zsh",
]);

const TEXT_FILENAMES = new Set([
  "dockerfile",
  "gemfile",
  "makefile",
  "procfile",
  ".editorconfig",
  ".gitattributes",
  ".gitignore",
  ".npmrc",
  ".prettierignore",
  ".prettierrc",
]);

/** Whether a workspace file is safe to load and edit as plain text. */
export function isProbablyText(name: string): boolean {
  const basename = name.split(/[\\/]/).pop()?.toLowerCase() ?? "";
  if (TEXT_FILENAMES.has(basename)) return true;
  const dot = basename.lastIndexOf(".");
  if (dot < 0 || dot === basename.length - 1) return false;
  return TEXT_EXTENSIONS.has(basename.slice(dot + 1));
}
