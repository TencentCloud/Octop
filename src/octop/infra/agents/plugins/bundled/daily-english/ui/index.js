const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function DailyEnglish(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  if (d.error) return null;
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 400,
      borderRadius: 20,
      padding: 18,
      background: dark ? "linear-gradient(165deg,#1e3a8a,#172554)" : "linear-gradient(165deg,#eff6ff,#dbeafe)",
      color: dark ? "#dbeafe" : "#1e3a8a",
      boxShadow: "0 12px 28px rgba(37,99,235,.18)",
    },
    "data-octop-plugin-ui": "daily-english",
    children: [
      _jsx("div", { style: { fontSize: 12, opacity: 0.75 }, children: d.daily ? `📘 今日单词 · ${d.date || ""}` : "📘 单词" }),
      _jsx("div", { style: { fontSize: 28, fontWeight: 800, margin: "8px 0 4px" }, children: d.word || "" }),
      _jsx("div", { style: { fontStyle: "italic", opacity: 0.85 }, children: d.phonetic || "" }),
      _jsx("div", { style: { marginTop: 10, fontWeight: 600 }, children: d.meaning_zh || "" }),
      _jsx("div", { style: { marginTop: 12, fontSize: 13, lineHeight: 1.5, opacity: 0.9 }, children: d.example || "" }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "daily_english_card", tools: ["daily_english"], component: DailyEnglish });
}
