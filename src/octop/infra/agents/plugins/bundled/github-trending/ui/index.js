const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function GithubTrending(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const items = Array.isArray(d.items) ? d.items : [];
  if (d.silent || items.length === 0) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 520,
      borderRadius: 18,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      border: dark ? "1px solid #3f3f46" : "1px solid #e4e4e7",
      boxShadow: "0 10px 28px rgba(0,0,0,.08)",
    },
    "data-octop-plugin-ui": "github-trending",
    children: [
      _jsxs("div", {
        style: {
          padding: "12px 14px",
          fontWeight: 800,
          background: dark ? "#27272a" : "linear-gradient(135deg,#f4f4f5,#e4e4e7)",
        },
        children: ["🐙 GitHub 趋势 · ", d.since || "daily", d.language ? ` · ${d.language}` : ""],
      }),
      _jsx("ol", {
        style: { margin: 0, padding: "8px 12px 12px", listStyle: "none" },
        children: items.map((row, i) =>
          _jsxs(
            "li",
            {
              style: { padding: "8px 4px", borderBottom: dark ? "1px solid #27272a" : "1px solid #f4f4f5" },
              children: [
                _jsxs("a", {
                  href: row.url || "#",
                  target: "_blank",
                  rel: "noopener noreferrer",
                  style: { color: "inherit", fontWeight: 700, textDecoration: "none" },
                  children: [row.full_name || row.name || ""],
                }),
                _jsx("div", { style: { fontSize: 12, opacity: 0.65, marginTop: 4 }, children: row.description || "" }),
                _jsxs("div", { style: { fontSize: 11, marginTop: 4, opacity: 0.8 }, children: ["⭐ ", row.stars, row.language ? ` · ${row.language}` : ""] }),
              ],
            },
            String(i),
          ),
        ),
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "github_trending_list", tools: ["github_trending"], component: GithubTrending });
}
