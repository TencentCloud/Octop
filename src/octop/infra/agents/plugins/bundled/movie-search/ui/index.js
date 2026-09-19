const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function MovieSearch(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const items = Array.isArray(d.items) ? d.items : [];
  if (d.silent || items.length === 0) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 480,
      borderRadius: 18,
      padding: 14,
      background: dark ? "#18181b" : "#fff",
      border: dark ? "1px solid #3f3f46" : "1px solid #fecdd3",
      boxShadow: "0 10px 28px rgba(225,29,72,.12)",
    },
    "data-octop-plugin-ui": "movie-search",
    children: [
      _jsxs("div", { style: { fontWeight: 800, marginBottom: 10 }, children: ["🎬 ", d.query || "搜索"] }),
      items.map((row, i) =>
        _jsxs(
          "div",
          {
            style: { display: "flex", gap: 10, marginBottom: 10, alignItems: "flex-start" },
            children: [
              row.image
                ? _jsx("img", { src: row.image, alt: "", style: { width: 48, height: 64, objectFit: "cover", borderRadius: 8 } })
                : null,
              _jsxs("div", { style: { flex: 1, minWidth: 0 }, children: [
                _jsx("a", {
                  href: row.url || "#",
                  target: "_blank",
                  rel: "noopener noreferrer",
                  style: { fontWeight: 700, color: "inherit", textDecoration: "none" },
                  children: row.title || "",
                }),
                _jsx("div", { style: { fontSize: 12, opacity: 0.7 }, children: row.score != null ? `评分 ${row.score}` : "" }),
                _jsx("div", { style: { fontSize: 12, opacity: 0.65, marginTop: 4 }, children: row.summary || "" }),
              ] }),
            ],
          },
          String(i),
        ),
      ),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "movie_search_card", tools: ["search_movie"], component: MovieSearch });
}
