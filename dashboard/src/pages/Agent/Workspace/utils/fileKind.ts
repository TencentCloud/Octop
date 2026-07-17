/**
 * Heuristics for classifying a workspace entry path.
 *
 * Kept separate from media/document classification so both the workspace
 * drawer and the shared ``FileViewer`` can reuse the same text-file test.
 */

export function isProbablyText(name: string): boolean {
  return /\.(md|txt|json|jsonl|yaml|yml|toml|py|ts|tsx|js|jsx|css|html|xml|csv|log|sh|env)$/i.test(
    name,
  );
}
