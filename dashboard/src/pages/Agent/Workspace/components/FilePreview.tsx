import { useEffect, useMemo, useState } from "react";
import {
  JsonView,
  allExpanded,
  darkStyles,
  defaultStyles,
} from "react-json-view-lite";
import "react-json-view-lite/dist/index.css";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneDark,
  oneLight,
} from "react-syntax-highlighter/dist/esm/styles/prism";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import Markdown from "../../../../components/Markdown/LazyMarkdown";
import styles from "../index.module.less";

SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("json", json);

export type PreviewKind =
  | "markdown"
  | "python"
  | "javascript"
  | "json"
  | "jsonl"
  | "html";

export function getPreviewKind(path: string): PreviewKind | null {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "md") return "markdown";
  if (ext === "py") return "python";
  if (ext === "js") return "javascript";
  if (ext === "json") return "json";
  if (ext === "jsonl") return "jsonl";
  if (ext === "html" || ext === "htm") return "html";
  return null;
}

/** Preview kinds that need a flex-filled host (e.g. iframe) rather than scrollable text. */
export function previewNeedsFillLayout(kind: PreviewKind | null): boolean {
  return kind === "html";
}

function useIsDark() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    setDark(mql.matches);
    const handler = (e: MediaQueryListEvent) => setDark(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return dark;
}

function CodeBlock({
  language,
  content,
}: {
  language: string;
  content: string;
}) {
  const isDark = useIsDark();
  return (
    <SyntaxHighlighter
      language={language}
      style={isDark ? oneDark : oneLight}
      customStyle={{
        margin: 0,
        borderRadius: 0,
        background: "transparent",
        fontSize: 12,
      }}
      codeTagProps={{
        style: { fontFamily: "var(--fn-font-mono, ui-monospace, monospace)" },
      }}
    >
      {content}
    </SyntaxHighlighter>
  );
}

function JsonPreview({ content }: { content: string }) {
  const parsed = useMemo(() => {
    try {
      return { ok: true as const, value: JSON.parse(content) };
    } catch {
      return { ok: false as const };
    }
  }, [content]);

  const isDark = useIsDark();
  if (!parsed.ok) {
    return <CodeBlock language="json" content={content} />;
  }

  return (
    <div className={styles.jsonPreview}>
      <JsonView
        data={parsed.value}
        style={isDark ? darkStyles : defaultStyles}
        shouldExpandNode={allExpanded}
      />
    </div>
  );
}

function JsonlLine({ index, line }: { index: number; line: string }) {
  const isDark = useIsDark();
  if (!line.trim()) {
    return <div className={styles.jsonlLine} />;
  }
  try {
    const value = JSON.parse(line);
    return (
      <div className={styles.jsonlLine}>
        <span className={styles.jsonlIndex}>{index + 1}</span>
        <JsonView
          data={value}
          style={isDark ? darkStyles : defaultStyles}
          shouldExpandNode={allExpanded}
          compactTopLevel
        />
      </div>
    );
  } catch {
    return (
      <div className={styles.jsonlLine}>
        <span className={styles.jsonlIndex}>{index + 1}</span>
        <CodeBlock language="json" content={line} />
      </div>
    );
  }
}

function JsonlPreview({ content }: { content: string }) {
  const lines = useMemo(
    () =>
      content
        .split("\n")
        .filter((line, idx, arr) => line.length > 0 || idx < arr.length - 1),
    [content],
  );

  return (
    <div className={styles.jsonlPreview}>
      {lines.map((line, idx) => (
        <JsonlLine key={idx} index={idx} line={line} />
      ))}
    </div>
  );
}

export default function FilePreview({
  kind,
  content,
}: {
  kind: PreviewKind;
  content: string;
}) {
  switch (kind) {
    case "markdown":
      return <Markdown content={content} className={styles.markdownPreview} />;
    case "python":
      return <CodeBlock language="python" content={content} />;
    case "javascript":
      return <CodeBlock language="javascript" content={content} />;
    case "json":
      return <JsonPreview content={content} />;
    case "jsonl":
      return <JsonlPreview content={content} />;
    case "html":
      // Render in a sandboxed iframe with an opaque origin (no
      // ``allow-same-origin``) so the previewed markup cannot reach our
      // cookies, JWT, or parent DOM. Scripts run in that isolated origin only.
      return (
        <iframe
          title="HTML preview"
          className={styles.htmlFrame}
          srcDoc={content}
          sandbox="allow-scripts allow-popups allow-forms"
        />
      );
    default:
      return null;
  }
}
