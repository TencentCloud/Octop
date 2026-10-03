/** Lazy mermaid core — diagram chunks load on first render of each type. */
let mermaidModule: typeof import("mermaid")["default"] | null = null;
let mermaidInitialised = false;

export async function loadMermaid() {
  if (!mermaidModule) {
    const mod = await import("mermaid");
    mermaidModule = mod.default;
  }
  if (!mermaidInitialised) {
    mermaidInitialised = true;
    mermaidModule.initialize({
      startOnLoad: false,
      theme: "default",
      // Diagram content comes from LLM / IM users, so it is untrusted input.
      // "loose" skips DOMPurify on the rendered SVG and permits click
      // handlers — a stored-XSS vector (audit SEC-5). "strict" keeps HTML
      // labels but sanitizes the SVG before it is attached to the DOM.
      securityLevel: "strict",
      fontFamily: "inherit",
    });
  }
  return mermaidModule;
}
