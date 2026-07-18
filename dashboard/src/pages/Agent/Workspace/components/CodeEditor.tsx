/**
 * CodeEditor — Monaco-based IDE editor for workspace text/code files.
 *
 * Lazy-loads ``@monaco-editor/react`` so the heavy editor bundle only
 * ships when a user actually edits a file. Language is derived from the
 * file extension via ``getEditorLanguage``.
 *
 * While an ancestor dock panel has ``data-dock-resizing``, automaticLayout
 * is paused so popup/right-panel resize stays smooth; layout() runs once
 * when resizing ends.
 */

import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Spin } from "antd";
import type { OnMount } from "@monaco-editor/react";
import { getEditorLanguage } from "../utils/editorLanguage";
import styles from "../index.module.less";

const MonacoEditor = lazy(() => import("@monaco-editor/react"));

function useIsDark(): boolean {
  const [dark, setDark] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-color-scheme: dark)").matches,
  );
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setDark(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return dark;
}

interface CodeEditorProps {
  path: string;
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
}

export default function CodeEditor({
  path,
  value,
  onChange,
  readOnly = false,
}: CodeEditorProps) {
  const language = getEditorLanguage(path);
  const isDark = useIsDark();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<{
    updateOptions: (opts: { automaticLayout?: boolean }) => void;
    layout: () => void;
  } | null>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const panel = wrap.closest("[data-dock-panel]");
    if (!panel) return;

    const sync = () => {
      const editor = editorRef.current;
      if (!editor) return;
      const resizing = panel.getAttribute("data-dock-resizing") === "1";
      editor.updateOptions({ automaticLayout: !resizing });
      if (!resizing) editor.layout();
    };

    sync();
    const mo = new MutationObserver(sync);
    mo.observe(panel, {
      attributes: true,
      attributeFilter: ["data-dock-resizing"],
    });
    return () => mo.disconnect();
  }, []);

  const handleMount: OnMount = (editor) => {
    editorRef.current = editor;
    const panel = wrapRef.current?.closest("[data-dock-panel]");
    if (panel?.getAttribute("data-dock-resizing") === "1") {
      editor.updateOptions({ automaticLayout: false });
    }
  };

  const fallback = (
    <div className={styles.viewerLoading}>
      <Spin />
    </div>
  );

  return (
    <div ref={wrapRef} className={styles.codeEditor}>
      <Suspense fallback={fallback}>
        <MonacoEditor
          height="100%"
          language={language}
          theme={isDark ? "vs-dark" : "light"}
          value={value}
          onChange={(v) => onChange(v ?? "")}
          onMount={handleMount}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            readOnly,
            wordWrap: "off",
            automaticLayout: true,
            tabSize: 2,
            renderWhitespace: "selection",
            fixedOverflowWidgets: true,
          }}
        />
      </Suspense>
    </div>
  );
}
