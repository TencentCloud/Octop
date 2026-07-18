import type { RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import Markdown from "../../../../components/Markdown/LazyMarkdown";
import styles from "../index.module.less";

/**
 * Rich preview kinds — documents that benefit from rendered view.
 * Source-code files (``.py`` / ``.js`` / ``.json`` / …) intentionally stay on
 * plain source mode: Prism/JSON-tree previews reflow heavily on panel resize.
 */
export type PreviewKind = "markdown" | "html";

export function getPreviewKind(path: string): PreviewKind | null {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "md" || ext === "markdown") return "markdown";
  if (ext === "html" || ext === "htm") return "html";
  return null;
}

/** Whether the file should open in preview (vs source) by default. */
export function defaultPreviewMode(path: string): boolean {
  return getPreviewKind(path) !== null;
}

/** Preview kinds that need a flex-filled host (e.g. iframe) rather than scrollable text. */
export function previewNeedsFillLayout(kind: PreviewKind | null): boolean {
  return kind === "html";
}

function useDockResizing(elRef: RefObject<HTMLElement | null>): boolean {
  const [resizing, setResizing] = useState(false);
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const panel = el.closest("[data-dock-panel]");
    if (!panel) return;
    const sync = () =>
      setResizing(panel.getAttribute("data-dock-resizing") === "1");
    sync();
    const mo = new MutationObserver(sync);
    mo.observe(panel, {
      attributes: true,
      attributeFilter: ["data-dock-resizing"],
    });
    return () => mo.disconnect();
  }, [elRef]);
  return resizing;
}

/**
 * During dock resize, freeze a DOM snapshot so markdown does not reflow (jank)
 * and the panel does not flash blank (unmount).
 */
function MarkdownPreview({ content }: { content: string }) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const liveRef = useRef<HTMLDivElement | null>(null);
  const freezeHtmlRef = useRef("");
  const heightRef = useRef(0);
  const [frozenHtml, setFrozenHtml] = useState<string | null>(null);
  const resizing = useDockResizing(wrapRef);

  useEffect(() => {
    if (resizing) {
      const live = liveRef.current;
      if (live && !frozenHtml) {
        heightRef.current = live.offsetHeight;
        freezeHtmlRef.current = live.innerHTML;
        setFrozenHtml(freezeHtmlRef.current);
      }
      return;
    }
    if (frozenHtml !== null) {
      setFrozenHtml(null);
    }
  }, [resizing, frozenHtml]);

  return (
    <div
      ref={wrapRef}
      className={styles.markdownPreviewHost}
      style={
        frozenHtml
          ? {
              minHeight: heightRef.current || undefined,
              overflow: "hidden",
              position: "relative",
            }
          : { position: "relative" }
      }
    >
      {frozenHtml ? (
        <div
          className={styles.markdownPreview}
          style={{ pointerEvents: "none" }}
          dangerouslySetInnerHTML={{ __html: frozenHtml }}
          aria-hidden
        />
      ) : (
        <div ref={liveRef}>
          <Markdown content={content} className={styles.markdownPreview} />
        </div>
      )}
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
      return <MarkdownPreview content={content} />;
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
