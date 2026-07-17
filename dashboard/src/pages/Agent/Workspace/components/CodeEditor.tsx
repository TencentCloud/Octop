/**
 * CodeEditor — Monaco-based IDE editor for workspace text/code files.
 *
 * Lazy-loads ``@monaco-editor/react`` so the heavy editor bundle only
 * ships when a user actually edits a file. Language is derived from the
 * file extension via ``getEditorLanguage``.
 */

import { lazy, Suspense, useEffect, useState } from "react";
import { Spin } from "antd";
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

  const fallback = (
    <div className={styles.viewerLoading}>
      <Spin />
    </div>
  );

  return (
    <div className={styles.codeEditor}>
      <Suspense fallback={fallback}>
        <MonacoEditor
          height="100%"
          language={language}
          theme={isDark ? "vs-dark" : "light"}
          value={value}
          onChange={(v) => onChange(v ?? "")}
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
