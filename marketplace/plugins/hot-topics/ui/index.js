const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

const THEMES = {
  weibo: { emoji: "🔥", title: "微博热搜", accent: "#f97316", bg: "linear-gradient(135deg,#fff7ed,#ffedd5)" },
  zhihu: { emoji: "💡", title: "知乎热榜", accent: "#0066ff", bg: "linear-gradient(135deg,#eff6ff,#dbeafe)" },
  hn: { emoji: "🟧", title: "Hacker News", accent: "#f97316", bg: "linear-gradient(135deg,#fff7ed,#fed7aa)" },
};

function HotTopics(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const items = Array.isArray(d.items) ? d.items : [];
  if (d.silent || d.error || items.length === 0) return null;
  const look = THEMES[d.source] || THEMES.weibo;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 520,
      borderRadius: 18,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      border: dark ? "1px solid #3f3f46" : "1px solid #fed7aa",
      boxShadow: "0 10px 28px rgba(249,115,22,.12)",
    },
    "data-octop-plugin-ui": "hot-topics",
    children: [
      _jsxs("div", {
        style: {
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "12px 14px",
          background: dark ? "#27272a" : look.bg,
          fontWeight: 800,
        },
        children: [
          _jsx("span", { style: { fontSize: 20 }, children: look.emoji }),
          _jsx("span", { children: look.title }),
        ],
      }),
      _jsx("ol", {
        style: { margin: 0, padding: "8px 12px 12px", listStyle: "none" },
        children: items.map((row) =>
          _jsxs(
            "li",
            {
              style: {
                display: "flex",
                gap: 10,
                alignItems: "flex-start",
                padding: "8px 4px",
                borderBottom: dark ? "1px solid #27272a" : "1px solid #fff7ed",
              },
              children: [
                _jsx("span", {
                  style: {
                    minWidth: 22,
                    height: 22,
                    borderRadius: 6,
                    background: Number(row.rank) <= 3 ? look.accent : dark ? "#3f3f46" : "#ffedd5",
                    color: Number(row.rank) <= 3 || dark ? "#fff" : "#9a3412",
                    fontSize: 12,
                    fontWeight: 800,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                  },
                  children: row.rank,
                }),
                _jsx("a", {
                  href: row.url || "#",
                  target: "_blank",
                  rel: "noopener noreferrer",
                  style: { color: "inherit", textDecoration: "none", flex: 1, fontWeight: 600, lineHeight: 1.4 },
                  children: row.title || "",
                }),
                row.extra
                  ? _jsx("span", { style: { fontSize: 11, opacity: 0.55, whiteSpace: "nowrap" }, children: String(row.extra) })
                  : null,
              ],
            },
            String(row.rank),
          ),
        ),
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({
    id: "hot_topics_list",
    tools: ["get_hot_topics"],
    component: HotTopics,
  });
}
