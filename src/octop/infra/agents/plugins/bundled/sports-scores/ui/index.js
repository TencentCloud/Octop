const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function SportsScores(props) {
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
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      border: dark ? "1px solid #3f3f46" : "1px solid #bbf7d0",
    },
    "data-octop-plugin-ui": "sports-scores",
    children: [
      _jsx("div", { style: { padding: "12px 14px", fontWeight: 800, background: dark ? "#14532d" : "#dcfce7" }, children: "⚽ 赛况" }),
      items.map((row, i) =>
        _jsxs(
          "div",
          {
            style: {
              padding: "10px 14px",
              borderBottom: dark ? "1px solid #27272a" : "1px solid #f0fdf4",
              display: "flex",
              justifyContent: "space-between",
              gap: 8,
              fontSize: 13,
            },
            children: [
              _jsxs("span", { style: { opacity: 0.65, minWidth: 72 }, children: [row.date || ""] }),
              _jsxs("span", { style: { flex: 1, fontWeight: 600 }, children: [row.home, " ", row.score, " ", row.away] }),
            ],
          },
          String(i),
        ),
      ),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "sports_scores_list", tools: ["sports_scores"], component: SportsScores });
}
