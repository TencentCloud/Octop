const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function ShortLink(props) {
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error || !d.shorturl) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 420,
      borderRadius: 14,
      padding: 14,
      background: "linear-gradient(135deg,#ecfeff,#cffafe)",
      border: "1px solid #67e8f9",
    },
    "data-octop-plugin-ui": "short-link",
    children: [
      _jsx("div", { style: { fontWeight: 800, marginBottom: 8 }, children: "🔗 短链接" }),
      _jsx("a", {
        href: d.shorturl,
        target: "_blank",
        rel: "noopener noreferrer",
        style: { fontWeight: 700, color: "#0e7490", wordBreak: "break-all" },
        children: d.shorturl,
      }),
      _jsx("div", { style: { fontSize: 11, marginTop: 8, opacity: 0.6, wordBreak: "break-all" }, children: d.url || "" }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "short_link_card", tools: ["make_short_link"], component: ShortLink });
}
