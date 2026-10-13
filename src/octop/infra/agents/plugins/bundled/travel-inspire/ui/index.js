const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function TravelInspire(props) {
  const theme = props.host.getToolContext().theme;
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  return _jsxs("div", {
    style: {
      margin: 0,
      maxWidth: 380,
      borderRadius: 20,
      padding: 18,
      background: dark ? "linear-gradient(165deg,#431407,#7c2d12)" : "linear-gradient(165deg,#fff7ed,#ffedd5)",
      boxShadow: "0 12px 28px rgba(234,88,12,.15)",
    },
    "data-octop-plugin-ui": "travel-inspire",
    children: [
      _jsx("div", { style: { fontSize: 12, opacity: 0.7 }, children: "✈️ 旅行灵感" }),
      _jsxs("div", { style: { fontSize: 24, fontWeight: 800, marginTop: 6 }, children: [d.city, " · ", d.country] }),
      _jsx("p", { style: { lineHeight: 1.55, margin: "10px 0" }, children: d.blurb || "" }),
      _jsxs("div", { style: { fontSize: 13, fontWeight: 700, opacity: 0.85 }, children: ["最佳季节：", d.best_season || "—"] }),
      Array.isArray(d.tags) && d.tags.length
        ? _jsx("div", { style: { marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }, children: d.tags.map((t) =>
            _jsx("span", { style: { fontSize: 11, padding: "4px 8px", borderRadius: 999, background: "rgba(255,255,255,.45)" }, children: t }, t),
          ) })
        : null,
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "travel_inspire_card", tools: ["travel_inspire"], component: TravelInspire });
}
