/**
 * Soft-close incomplete Markdown constructs while a reply is still streaming.
 * Without this, an open fence (` ``` `) makes remark swallow the rest of the
 * document as a code block until the closing fence arrives — causing a big
 * layout jump ("jitter") on every few tokens.
 */
export function stabilizeStreamingMarkdown(content: string): string {
  if (!content) return content;

  let result = content;

  // Unclosed fenced code block (odd number of fence openers at line start).
  const fenceOpens = result.match(/^ {0,3}(`{3,}|~{3,})/gm);
  if (fenceOpens && fenceOpens.length % 2 === 1) {
    const last = fenceOpens[fenceOpens.length - 1] ?? "```";
    const marker = last.trim()[0] === "~" ? "~~~" : "```";
    result += result.endsWith("\n") ? marker : `\n${marker}`;
  }

  return result;
}
