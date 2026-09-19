const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function WikiSummary(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.silent || d.error) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 480,
      borderRadius: 18,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      border: dark ? "1px solid #3f3f46" : "1px solid #bfdbfe",
    },
    "data-octop-plugin-ui": "wiki-summary",
    children: [
      d.thumbnail
        ? _jsx("img", { src: d.thumbnail, alt: "", style: { width: "100%", maxHeight: 160, objectFit: "cover" } })
        : null,
      _jsxs("div", { style: { padding: 14 }, children: [
        _jsx("a", {
          href: d.url || "#",
          target: "_blank",
          rel: "noopener noreferrer",
          style: { fontWeight: 800, fontSize: 16, color: "inherit", textDecoration: "none" },
          children: d.title || d.query || "维基",
        }),
        _jsx("p", { style: { margin: "10px 0 0", lineHeight: 1.55, fontSize: 14, opacity: 0.9 }, children: d.extract || "" }),
      ] }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "wiki_summary_card", tools: ["wiki_summary"], component: WikiSummary });
}
