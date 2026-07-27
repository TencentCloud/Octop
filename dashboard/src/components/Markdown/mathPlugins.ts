import { useEffect, useState } from "react";
import type { PluggableList } from "unified";

const MATH_PATTERN =
  /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?:^|[^\w$\\])\$[^\n$]+\$(?:$|[^\w$])/m;

export function contentHasMath(content: string): boolean {
  return MATH_PATTERN.test(content);
}

let katexCssLoaded = false;

export function ensureKatexCss() {
  if (katexCssLoaded || typeof document === "undefined") return;
  katexCssLoaded = true;
  void import("katex/dist/katex.min.css");
}

type MathPlugins = {
  remarkPlugins: PluggableList;
  rehypePlugins: PluggableList;
};

const EMPTY_PLUGINS: MathPlugins = {
  remarkPlugins: [],
  rehypePlugins: [],
};

/** Module-level cache so streaming token updates do not rebuild plugin arrays. */
let cachedMathPlugins: MathPlugins | null = null;
let mathPluginsPromise: Promise<MathPlugins> | null = null;

function loadMathPlugins(): Promise<MathPlugins> {
  if (cachedMathPlugins) return Promise.resolve(cachedMathPlugins);
  if (!mathPluginsPromise) {
    mathPluginsPromise = Promise.all([
      import("remark-math"),
      import("rehype-katex"),
    ]).then(([remarkMath, rehypeKatex]) => {
      ensureKatexCss();
      cachedMathPlugins = {
        remarkPlugins: [remarkMath.default],
        rehypePlugins: [rehypeKatex.default],
      };
      return cachedMathPlugins;
    });
  }
  return mathPluginsPromise;
}

/**
 * Lazy-load KaTeX remark/rehype plugins when content looks like math.
 *
 * Important: depend on `hasMath` only — never on full `content`. Streaming
 * updates used to re-run this effect every token and remount ReactMarkdown,
 * which showed up as visible jitter in the chat bubble.
 */
export function useMathPlugins(content: string): MathPlugins {
  const hasMath = contentHasMath(content);
  const [plugins, setPlugins] = useState<MathPlugins>(() =>
    hasMath && cachedMathPlugins ? cachedMathPlugins : EMPTY_PLUGINS,
  );

  useEffect(() => {
    if (!hasMath) {
      setPlugins(EMPTY_PLUGINS);
      return;
    }
    if (cachedMathPlugins) {
      setPlugins(cachedMathPlugins);
      return;
    }
    let cancelled = false;
    void loadMathPlugins().then((loaded) => {
      if (!cancelled) setPlugins(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [hasMath]);

  return plugins;
}
