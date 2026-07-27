import {
  useEffect,
  useState,
  type ComponentType,
  type CSSProperties,
} from "react";
import type { SyntaxHighlighterProps } from "react-syntax-highlighter";

type HighlightStyle = { [key: string]: CSSProperties };

type PrismLight = ComponentType<SyntaxHighlighterProps>;

type HighlighterModule = PrismLight & {
  registerLanguage: (name: string, lang: unknown) => void;
};

const registeredLanguages = new Set<string>();
let highlighterPromise: Promise<HighlighterModule> | null = null;
let stylePromise: Promise<{
  light: HighlightStyle;
  dark: HighlightStyle;
}> | null = null;

async function getSyntaxHighlighter(): Promise<HighlighterModule> {
  if (!highlighterPromise) {
    highlighterPromise = import(
      "react-syntax-highlighter/dist/esm/prism-light"
    ).then((mod) => mod.default as unknown as HighlighterModule);
  }
  return highlighterPromise;
}

async function getHighlightStyles() {
  if (!stylePromise) {
    stylePromise = Promise.all([
      import("react-syntax-highlighter/dist/esm/styles/prism/one-light"),
      import("react-syntax-highlighter/dist/esm/styles/prism/one-dark"),
    ]).then(([lightMod, darkMod]) => ({
      light: lightMod.default,
      dark: darkMod.default,
    }));
  }
  return stylePromise;
}

async function loadLanguageModule(language: string): Promise<unknown | null> {
  switch (language.toLowerCase()) {
    case "tsx":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/tsx")
      ).default;
    case "typescript":
      return (
        await import(
          "react-syntax-highlighter/dist/esm/languages/prism/typescript"
        )
      ).default;
    case "javascript":
      return (
        await import(
          "react-syntax-highlighter/dist/esm/languages/prism/javascript"
        )
      ).default;
    case "python":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/python")
      ).default;
    case "bash":
    case "shell":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/bash")
      ).default;
    case "json":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/json")
      ).default;
    case "css":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/css")
      ).default;
    case "sql":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/sql")
      ).default;
    case "yaml":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/yaml")
      ).default;
    case "markdown":
      return (
        await import(
          "react-syntax-highlighter/dist/esm/languages/prism/markdown"
        )
      ).default;
    case "go":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/go")
      ).default;
    case "rust":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/rust")
      ).default;
    case "java":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/java")
      ).default;
    case "c":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/c")
      ).default;
    case "cpp":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/cpp")
      ).default;
    case "docker":
    case "dockerfile":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/docker")
      ).default;
    case "diff":
      return (
        await import("react-syntax-highlighter/dist/esm/languages/prism/diff")
      ).default;
    default:
      return null;
  }
}

async function ensureLanguage(
  highlighter: HighlighterModule,
  language: string,
) {
  const normalized = language.toLowerCase();
  if (registeredLanguages.has(normalized)) return;

  const langModule = await loadLanguageModule(normalized);
  if (langModule) {
    highlighter.registerLanguage(normalized, langModule);
    if (normalized === "bash") {
      highlighter.registerLanguage("shell", langModule);
    }
    if (normalized === "docker") {
      highlighter.registerLanguage("dockerfile", langModule);
    }
  }
  registeredLanguages.add(normalized);
}

interface HighlightedCodeProps {
  language: string;
  code: string;
  isDark: boolean;
  /** Prefer plain `<pre>` while streaming; highlighter still preloads in the background. */
  plain?: boolean;
}

const plainCodeStyle: CSSProperties = {
  margin: 0,
  borderRadius: "0 0 8px 8px",
  fontSize: 13,
  padding: "12px 16px",
  overflow: "auto",
};

export function HighlightedCode({
  language,
  code,
  isDark,
  plain = false,
}: HighlightedCodeProps) {
  const [SyntaxHighlighter, setSyntaxHighlighter] = useState<PrismLight | null>(
    null,
  );
  const [highlightStyle, setHighlightStyle] = useState<HighlightStyle | null>(
    null,
  );

  // Preload highlighter during streaming so the plain→colored switch is one paint,
  // not a delayed second jump after the stream ends.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [highlighter, styles] = await Promise.all([
        getSyntaxHighlighter(),
        getHighlightStyles(),
      ]);
      await ensureLanguage(highlighter, language);
      if (!cancelled) {
        setSyntaxHighlighter(() => highlighter);
        setHighlightStyle(isDark ? styles.dark : styles.light);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [language, isDark]);

  if (plain || !SyntaxHighlighter || !highlightStyle) {
    return (
      <pre style={plainCodeStyle}>
        <code>{code}</code>
      </pre>
    );
  }

  return (
    <SyntaxHighlighter
      style={highlightStyle}
      language={language.toLowerCase()}
      PreTag="div"
      customStyle={{
        margin: 0,
        borderRadius: "0 0 8px 8px",
        fontSize: 13,
        padding: "12px 16px",
      }}
    >
      {code}
    </SyntaxHighlighter>
  );
}
