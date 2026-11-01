import { useEffect, useId, useMemo, useRef, useState } from "react";
import styles from "./HtmlArtifactPreview.module.less";

/** Build a self-contained, opaque-origin preview. Never inject into the host DOM. */
export function htmlPreviewDocument(content: string, instance: string): string {
  const doc = new DOMParser().parseFromString(content, "text/html");
  doc.querySelectorAll("base, meta[http-equiv]").forEach((el) => el.remove());
  const policy = doc.createElement("meta");
  policy.httpEquiv = "Content-Security-Policy";
  policy.content =
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
    "img-src data: blob:; font-src data:; connect-src 'none'; " +
    "base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'none'";
  doc.head.prepend(policy);
  const script = doc.createElement("script");
  script.textContent = `
    addEventListener('DOMContentLoaded', () => {
      const report = () => parent.postMessage({
        type: 'octop-html-height', instance: ${JSON.stringify(instance)},
        height: Math.ceil(document.body.getBoundingClientRect().height +
          parseFloat(getComputedStyle(document.body).marginTop || 0) +
          parseFloat(getComputedStyle(document.body).marginBottom || 0))
      }, '*');
      new ResizeObserver(report).observe(document.body);
      report();
      // External navigation is not part of the self-contained preview contract.
      document.addEventListener('click', event => {
        const link = event.target.closest?.('a');
        if (link && !link.getAttribute('href')?.startsWith('#')) event.preventDefault();
      }, true);
    });`;
  doc.head.append(script);
  return "<!doctype html>" + doc.documentElement.outerHTML;
}

export default function HtmlArtifactPreview({
  content,
  title,
  mode = "panel",
}: {
  content: string;
  title: string;
  mode?: "inline" | "panel";
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const instance = useId();
  const [height, setHeight] = useState(360);
  const srcDoc = useMemo(
    () => htmlPreviewDocument(content, instance),
    [content, instance],
  );
  useEffect(() => {
    setHeight(360);
    const resize = (event: MessageEvent<unknown>) => {
      if (event.source !== frame.current?.contentWindow) return;
      const data = event.data;
      if (!data || typeof data !== "object") return;
      const message = data as Record<string, unknown>;
      if (
        message.type !== "octop-html-height" ||
        message.instance !== instance ||
        typeof message.height !== "number" ||
        !Number.isFinite(message.height)
      )
        return;
      setHeight(Math.max(200, Math.min(800, Math.ceil(message.height))));
    };
    window.addEventListener("message", resize);
    return () => window.removeEventListener("message", resize);
  }, [srcDoc, instance]);
  return (
    <iframe
      ref={frame}
      title={title}
      className={mode === "inline" ? styles.inline : styles.panel}
      style={mode === "inline" ? { height } : undefined}
      srcDoc={srcDoc}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
    />
  );
}
